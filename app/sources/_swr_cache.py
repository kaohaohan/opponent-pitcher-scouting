"""A tiny generic stale-while-revalidate cache.

Three zones, keyed off how long ago an entry was fetched (`time.monotonic`):

- younger than `fresh_ttl`: return the cached value, no upstream call.
- between `fresh_ttl` and `max_stale`: return the cached value immediately,
  *and* kick off a single background refresh for that key so the next caller
  (once it lands) gets something fresher. Concurrent callers in this window
  never queue more than one refresh per key.
- older than `max_stale`, or missing entirely: block and call the loader
  synchronously. Concurrent callers in this state serialize on a per-key
  lock and double-check the cache, so only one of them actually calls the
  loader.

A loader that raises is never cached — neither the synchronous path nor a
background refresh will poison the cache with an error, and a failed
background refresh just leaves the previous stale value in place (logged,
not raised, since nothing is waiting on it).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Executor
from dataclasses import dataclass
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class _Entry(Generic[V]):
    fetched_at: float
    value: V


class _SynchronousExecutor(Executor):
    """Runs "background" refreshes inline; used to keep tests deterministic."""

    def submit(self, fn, /, *args, **kwargs):  # type: ignore[override]
        fn(*args, **kwargs)


class SWRCache(Generic[K, V]):
    """A process-wide, in-memory stale-while-revalidate cache.

    Args:
        fresh_ttl: seconds an entry is served with no upstream call at all.
        max_stale: seconds an entry may be served while a background refresh
            is in flight. Older than this, callers block on a synchronous
            load instead.
        executor: where background refreshes run. Defaults to a real
            background thread per refresh; pass a synchronous executor (see
            `synchronous_executor`) to make refreshes happen inline, which
            is what deterministic tests want.
    """

    def __init__(
        self,
        fresh_ttl: float,
        max_stale: float,
        executor: Executor | None = None,
    ) -> None:
        if fresh_ttl < 0 or max_stale < fresh_ttl:
            raise ValueError("expected 0 <= fresh_ttl <= max_stale")
        self.fresh_ttl = fresh_ttl
        self.max_stale = max_stale
        self._executor = executor
        self._entries: dict[K, _Entry[V]] = {}
        self._entries_lock = threading.Lock()
        self._load_locks: dict[K, threading.Lock] = {}
        self._refreshing: set[K] = set()
        self._refreshing_lock = threading.Lock()

    def get(self, key: K, loader: Callable[[], V]) -> V:
        """Return a value for `key`, calling `loader` per the zone rules above."""
        now = time.monotonic()
        with self._entries_lock:
            entry = self._entries.get(key)

        if entry is not None:
            age = now - entry.fetched_at
            if age < self.fresh_ttl:
                return entry.value
            if age < self.max_stale:
                self._start_background_refresh(key, loader)
                return entry.value

        return self._load_synchronously(key, loader)

    def clear(self) -> None:
        """Drop every cached entry and forget in-flight refresh bookkeeping.

        Per-key load locks are intentionally left alone: a thread that is
        mid-load still holds its lock, and clearing the mapping cannot
        interrupt it. That is fine — the next `get()` after clear() will
        either see no entry (and load) or reuse a lock that is about to be
        released, never a stuck one.
        """
        with self._entries_lock:
            self._entries.clear()
        with self._refreshing_lock:
            self._refreshing.clear()

    def _lock_for(self, key: K) -> threading.Lock:
        with self._entries_lock:
            return self._load_locks.setdefault(key, threading.Lock())

    def _load_synchronously(self, key: K, loader: Callable[[], V]) -> V:
        lock = self._lock_for(key)
        with lock:
            # Double-checked: another thread may have populated (or
            # refreshed) the entry while we were waiting for the lock.
            with self._entries_lock:
                entry = self._entries.get(key)
            if entry is not None and time.monotonic() - entry.fetched_at < self.max_stale:
                return entry.value
            value = loader()
            with self._entries_lock:
                self._entries[key] = _Entry(time.monotonic(), value)
            return value

    def _start_background_refresh(self, key: K, loader: Callable[[], V]) -> None:
        with self._refreshing_lock:
            if key in self._refreshing:
                return
            self._refreshing.add(key)

        def refresh() -> None:
            try:
                value = loader()
            except Exception:  # noqa: BLE001 - never let a background refresh crash
                logger.warning(
                    "SWRCache background refresh failed for key=%r; keeping stale value",
                    key,
                    exc_info=True,
                )
                return
            with self._entries_lock:
                self._entries[key] = _Entry(time.monotonic(), value)

        def refresh_and_release() -> None:
            try:
                refresh()
            finally:
                with self._refreshing_lock:
                    self._refreshing.discard(key)

        executor = self._executor or _background_executor()
        executor.submit(refresh_and_release)


_default_executor: Executor | None = None
_default_executor_lock = threading.Lock()


def _background_executor() -> Executor:
    """A lazily-created, shared thread-per-task executor for real refreshes."""
    global _default_executor
    with _default_executor_lock:
        if _default_executor is None:
            from concurrent.futures import ThreadPoolExecutor

            _default_executor = ThreadPoolExecutor(
                max_workers=8, thread_name_prefix="swr-cache-refresh"
            )
        return _default_executor


def synchronous_executor() -> Executor:
    """An executor that runs "background" refreshes inline, for tests."""
    return _SynchronousExecutor()
