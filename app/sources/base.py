"""The source interface.

A source's only job is to yield plate-appearance events already shaped like
`app.schemas.PlateAppearanceEvent`. Everything feed-specific — HTTP calls,
polling, MLB's field names, unit conversions — stays behind this interface, so
`ReplaySource` and `LiveSource` are interchangeable from the
processor's point of view.

Sources deliberately emit plain mappings rather than validated models: the
processor owns validation, so a malformed event from one source cannot be
silently dropped inside that source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from typing import Any

RawEvent = Mapping[str, Any]


class PlateAppearanceSource(ABC):
    """Produces normalized plate-appearance events in order.

    Each yielded mapping must use the field names of
    `app.schemas.PlateAppearanceEvent`. Statcast fields that the feed did not
    measure must be omitted or set to `None` — never to `0`.
    """

    #: Short identifier used in logs and in the replay report.
    name: str = "source"

    @abstractmethod
    def events(self) -> Iterator[RawEvent]:
        """Yield events oldest-first.

    Sources may be finite (including a one-shot live snapshot) or may block
    between events; the processor treats both forms identically.
        """

    def __iter__(self) -> Iterator[RawEvent]:
        return self.events()
