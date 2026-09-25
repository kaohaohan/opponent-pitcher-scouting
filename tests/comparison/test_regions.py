"""Plate attack-region classification."""

from __future__ import annotations

import pytest

from app.comparison.regions import Region, classify_region

SZ_TOP = 3.5
SZ_BOT = 1.5
MID = (SZ_TOP + SZ_BOT) / 2  # 2.5
HALF_H = (SZ_TOP - SZ_BOT) / 2  # 1.0
HALF_W = 10 / 12


def _at_distance(distance: float) -> float:
    """A plate_z value `distance` zone-units above the zone middle (plate_x=0)."""
    return MID + distance * HALF_H


def test_one_point_per_region():
    assert classify_region(0, MID, SZ_TOP, SZ_BOT) == Region.HEART
    assert classify_region(0, _at_distance(1.0), SZ_TOP, SZ_BOT) == Region.SHADOW
    assert classify_region(0, _at_distance(1.5), SZ_TOP, SZ_BOT) == Region.CHASE
    assert classify_region(0, _at_distance(2.5), SZ_TOP, SZ_BOT) == Region.WASTE


@pytest.mark.parametrize(
    "distance,inside,outside",
    [
        (2 / 3, Region.HEART, Region.SHADOW),
        (4 / 3, Region.SHADOW, Region.CHASE),
        (2.0, Region.CHASE, Region.WASTE),
    ],
)
def test_boundaries_are_half_open_to_the_outer_region(distance, inside, outside):
    # Offsets are ±1e-9 feet on plate_z, not ±1e-9 in zone-distance units —
    # this dwarfs the float rounding error (~1e-16) from reconstructing the
    # boundary through `mid + distance * half_h`, so the two assertions
    # reliably land on either side of the boundary.
    boundary = _at_distance(distance)
    just_inside = boundary - 1e-9
    just_outside = boundary + 1e-9

    assert classify_region(0, just_inside, SZ_TOP, SZ_BOT) == inside
    assert classify_region(0, just_outside, SZ_TOP, SZ_BOT) == outside


def test_exact_waste_boundary_case():
    assert classify_region(0, 4.5, 3.5, 1.5) == Region.WASTE


@pytest.mark.parametrize(
    "plate_x,plate_z,sz_top,sz_bot",
    [
        (None, 2.5, 3.5, 1.5),
        (0, None, 3.5, 1.5),
        (0, 2.5, None, 1.5),
        (0, 2.5, 3.5, None),
        (float("nan"), 2.5, 3.5, 1.5),
        (0, float("inf"), 3.5, 1.5),
        (0, 2.5, float("nan"), 1.5),
        (0, 2.5, 3.5, float("-inf")),
        (True, 2.5, 3.5, 1.5),
        (0, False, 3.5, 1.5),
    ],
)
def test_none_nan_inf_and_bool_inputs_return_none(plate_x, plate_z, sz_top, sz_bot):
    assert classify_region(plate_x, plate_z, sz_top, sz_bot) is None


def test_sz_top_must_be_strictly_greater_than_sz_bot():
    assert classify_region(0, 2.5, 2.5, 2.5) is None
    assert classify_region(0, 2.5, 1.5, 3.5) is None


def test_negative_plate_x_is_symmetric():
    for distance in (0.5, 1.0, 1.5, 2.5):
        x = distance * HALF_W
        assert classify_region(x, MID, SZ_TOP, SZ_BOT) == classify_region(
            -x, MID, SZ_TOP, SZ_BOT
        )
