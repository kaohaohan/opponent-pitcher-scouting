"""Plate attack-region classification (heart/shadow/chase/waste).

This is a reconstruction of the published chart, not a verified match to
Savant's implementation: the region boundaries are read off the zone
diagram linked from Baseball Savant's Swing/Take page
(tangotiger.net/strikezone/zone chart.png), not derived from Savant's own
source. Treat the resulting labels as descriptive, not authoritative.

Pure function, no I/O: takes the same plate-coordinate/strike-zone inputs
`app.comparison.locations` already extracts from a live feed snapshot.
"""

from __future__ import annotations

import math
from enum import StrEnum

#: Half the width of the "zone" used for region scaling: the 17-inch plate
#: plus one ball width (~3 in) on each side, expressed in feet and halved.
_HALF_ZONE_WIDTH_FT = 10 / 12


class Region(StrEnum):
    HEART = "heart"
    SHADOW = "shadow"
    CHASE = "chase"
    WASTE = "waste"


def classify_region(
    plate_x: float | None,
    plate_z: float | None,
    sz_top: float | None,
    sz_bot: float | None,
) -> Region | None:
    """Classify one pitch's plate location into a heart/shadow/chase/waste
    region, scaled to this batter's own strike zone.

    Returns `None` when any input is missing, non-finite, a bool, or when
    `sz_top <= sz_bot` — the same invalid-zone rule `compute_pitch_locations`
    uses (`app/comparison/locations.py`), since a degenerate zone can't be
    used to scale a region distance either.

    Boundaries are half-open on the inside: a point exactly on a boundary
    belongs to the outer region (`d < threshold`, not `<=`).
    """
    for value in (plate_x, plate_z, sz_top, sz_bot):
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        if not math.isfinite(value):
            return None
    if sz_top <= sz_bot:
        return None

    mid = (sz_top + sz_bot) / 2
    half_h = (sz_top - sz_bot) / 2

    distance = max(abs(plate_x) / _HALF_ZONE_WIDTH_FT, abs(plate_z - mid) / half_h)
    if distance < 2 / 3:
        return Region.HEART
    if distance < 4 / 3:
        return Region.SHADOW
    if distance < 2:
        return Region.CHASE
    return Region.WASTE
