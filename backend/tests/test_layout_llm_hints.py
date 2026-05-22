from app.schemas.semantic_layout import RoomPlacement
from app.services.default_semantic_layout import _apply_default_position_hints
from app.services.layout_llm_hints import (
    corner_from_normalized_center,
    target_area_from_hint,
)
from app.services.layout_postprocess import _close_neighbor_gaps, _expand_rooms_to_fill
from app.schemas.layout import LayoutRoom
from app.services.layout_geometry import rect_to_polygon


def test_corner_from_normalized_center():
    assert corner_from_normalized_center(0.1, 0.1) == "BL"
    assert corner_from_normalized_center(0.9, 0.9) == "TR"


def test_target_area_from_hint_blends():
    area = target_area_from_hint(20.0, 0.4, 0.3, 100.0, blend=0.5)
    assert 10.0 < area < 20.0


def test_default_position_hints_assign_centers():
    placements = [
        RoomPlacement(room_type="客厅", index=1),
        RoomPlacement(room_type="主卧", index=1),
    ]
    from app.schemas.semantic_layout import LayoutBand

    bands = [LayoutBand(order=["客厅"]), LayoutBand(order=["主卧"])]
    _apply_default_position_hints(placements, bands)
    assert placements[0].center_x >= 0.05
    assert placements[0].width_ratio > 0.05


def test_adhesion_closes_horizontal_gap():
    r1 = LayoutRoom(
        id="r1", name="A", type="", polygon=rect_to_polygon(0, 0, 4, 4), area_sqm=16,
    )
    r2 = LayoutRoom(
        id="r2", name="B", type="", polygon=rect_to_polygon(4.3, 0, 8, 4), area_sqm=15,
    )
    rooms = [(r1, (0, 0, 4, 4)), (r2, (4.3, 0, 8, 4))]
    poly = [(0, 0), (10, 0), (10, 6), (0, 6)]
    closed = _close_neighbor_gaps(rooms, poly)
    assert closed >= 1
    assert abs(rooms[0][1][2] - rooms[1][1][0]) < 0.05


def test_adhesion_expand_fills_toward_outline():
    r1 = LayoutRoom(
        id="r1", name="A", type="", polygon=rect_to_polygon(1, 1, 3, 3), area_sqm=4,
    )
    rooms = [(r1, (1, 1, 3, 3))]
    poly = [(0, 0), (6, 0), (6, 6), (0, 6)]
    expanded = _expand_rooms_to_fill(rooms, poly)
    assert expanded >= 1
    assert rooms[0][1][0] <= 1.0
