"""Live source — interface only.

Intentionally unimplemented. It exists so the shape of the eventual MLB
integration is pinned down now: a live feed is polled, it tracks which at-bats
it has already seen per game, and it emits the *same* normalized events as
`ReplaySource`. Because idempotency is enforced by the database
(`UNIQUE(game_id, at_bat_index)`), a live source is free to re-emit events it is
unsure about rather than keeping perfect client-side state.
"""

from __future__ import annotations

from collections.abc import Iterator

from .base import PlateAppearanceSource, RawEvent


class LiveSource(PlateAppearanceSource):
    """Polls a live game feed for newly completed plate appearances.

    Args:
        game_id: The game to follow.
        watched_player_ids: External player ids to emit events for.
        poll_interval_seconds: Delay between polls of the upstream feed.
    """

    name = "live"

    def __init__(
        self,
        game_id: str,
        watched_player_ids: tuple[str, ...] = (),
        poll_interval_seconds: float = 15.0,
    ) -> None:
        self.game_id = game_id
        self.watched_player_ids = watched_player_ids
        self.poll_interval_seconds = poll_interval_seconds

    def events(self) -> Iterator[RawEvent]:
        raise NotImplementedError(
            "LiveSource is not implemented yet. Implement fetch + normalization "
            "against a real MLB feed here; the processor needs no changes."
        )
