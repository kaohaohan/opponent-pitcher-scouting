"""Unit tests for the generic stale-while-revalidate cache helper."""

from __future__ import annotations

import threading
import time

import pytest

from app.sources._swr_cache import SWRCache, synchronous_executor


def _counting_loader(values):
    """A loader that pops from `values` each call and records call count."""
    calls: list[None] = []

    def loader():
        calls.append(None)
        return values[len(calls) - 1]

    return loader, calls


def test_fresh_hit_never_calls_the_loader_again():
    cache: SWRCache[str, int] = SWRCache(fresh_ttl=10.0, max_stale=60.0)
    loader, calls = _counting_loader([1, 2, 3])

    first = cache.get("k", loader)
    second = cache.get("k", loader)

    assert first == 1
    assert second == 1
    assert len(calls) == 1


def test_stale_returns_immediately_and_triggers_exactly_one_refresh(monkeypatch):
    fake_now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    cache: SWRCache[str, int] = SWRCache(
        fresh_ttl=10.0, max_stale=60.0, executor=synchronous_executor()
    )
    loader, calls = _counting_loader([1, 2, 3])

    first = cache.get("k", loader)
    assert first == 1
    assert len(calls) == 1

    fake_now[0] = 15.0  # past fresh_ttl, still within max_stale
    second = cache.get("k", loader)
    # Old value returned immediately...
    assert second == 1
    # ...and exactly one background refresh happened (synchronous executor
    # makes it happen inline, so it is already reflected in `calls`).
    assert len(calls) == 2

    # The refreshed value is now fresh again.
    third = cache.get("k", loader)
    assert third == 2
    assert len(calls) == 2


def test_stale_zone_only_starts_one_refresh_even_with_concurrent_callers(monkeypatch):
    fake_now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    started = threading.Event()
    release = threading.Event()
    calls: list[None] = []

    def slow_loader():
        calls.append(None)
        started.set()
        release.wait(timeout=5)
        return len(calls)

    cache: SWRCache[str, int] = SWRCache(fresh_ttl=10.0, max_stale=60.0)
    cache.get("k", lambda: 1)

    fake_now[0] = 15.0
    threads = [
        threading.Thread(target=cache.get, args=("k", slow_loader)) for _ in range(5)
    ]
    for thread in threads:
        thread.start()
    assert started.wait(timeout=5)
    release.set()
    for thread in threads:
        thread.join(timeout=5)

    assert len(calls) == 1


def test_too_stale_loads_synchronously():
    cache: SWRCache[str, int] = SWRCache(fresh_ttl=1.0, max_stale=2.0)
    loader, calls = _counting_loader([1, 2])

    cache.get("k", loader)
    time.sleep(2.1)
    value = cache.get("k", loader)

    assert value == 2
    assert len(calls) == 2


def test_loader_errors_are_never_cached():
    cache: SWRCache[str, int] = SWRCache(fresh_ttl=10.0, max_stale=60.0)
    attempts = [None]

    def flaky_loader():
        attempts[0] = (attempts[0] or 0) + 1
        raise RuntimeError("upstream boom")

    with pytest.raises(RuntimeError):
        cache.get("k", flaky_loader)
    with pytest.raises(RuntimeError):
        cache.get("k", flaky_loader)

    assert attempts[0] == 2


def test_failed_background_refresh_keeps_the_stale_value(monkeypatch):
    fake_now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    cache: SWRCache[str, int] = SWRCache(
        fresh_ttl=10.0, max_stale=60.0, executor=synchronous_executor()
    )

    cache.get("k", lambda: 1)

    fake_now[0] = 15.0

    def failing_loader():
        raise RuntimeError("refresh boom")

    value = cache.get("k", failing_loader)
    assert value == 1  # stale value still served, refresh failure swallowed

    # And a later call still sees the old value (still within max_stale).
    again = cache.get("k", lambda: 99)
    assert again == 1


def test_concurrent_synchronous_loads_call_the_loader_once():
    cache: SWRCache[str, int] = SWRCache(fresh_ttl=10.0, max_stale=60.0)
    started = threading.Event()
    release = threading.Event()
    calls: list[None] = []

    def slow_loader():
        calls.append(None)
        started.set()
        release.wait(timeout=5)
        return 42

    threads = [
        threading.Thread(target=cache.get, args=("k", slow_loader)) for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    assert started.wait(timeout=5)
    release.set()
    for thread in threads:
        thread.join(timeout=5)

    assert len(calls) == 1
    assert cache.get("k", lambda: -1) == 42
