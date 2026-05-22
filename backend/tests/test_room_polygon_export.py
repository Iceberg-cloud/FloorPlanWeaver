"""Room polygon export must match rectilinear cell unions (no bow-tie scanline artifacts)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.layout_grid import CELL_AREA, GridMap
from app.services.layout_geometry import polygon_area


def _l_shape_grid() -> tuple[GridMap, int]:
    inside = [
        [True, True, True, False],
        [True, False, False, False],
        [False, False, False, False],
    ]
    g = GridMap(0, 0, 4, 3, inside)
    g.rid = [[0] * 4 for _ in range(3)]
    rid = 1
    for i in range(3):
        g.rid[0][i] = rid
    g.rid[1][0] = rid
    return g, rid


def test_boundary_polygon_matches_cell_area_for_l_shape():
    g, rid = _l_shape_grid()
    pts = g.cells_to_boundary_polygon(rid)
    assert len(pts) >= 6
    expected = 4 * CELL_AREA
    assert abs(polygon_area(pts) - expected) < 1e-6


def test_scanline_polygon_no_longer_self_intersects_l_shape():
    g, rid = _l_shape_grid()
    pts = g.cells_to_polygon(rid)
    assert len(pts) >= 6
    expected = 4 * CELL_AREA
    assert abs(polygon_area(pts) - expected) < 1e-6


def test_grid_search_compiler_uses_boundary_for_polygon_rooms():
    from app.services.layout_grid_search_compiler import _export_rooms_from_state
    from app.schemas.layout_constraints import RoomPlacementConstraint

    g, rid = _l_shape_grid()

    living = "\u5ba2\u5385"  # 客厅
    c = RoomPlacementConstraint(
        name=living,
        room_type=living,
        target_area_sqm=1.0,
        must_be_rectangle=False,
    )

    from types import SimpleNamespace

    state = SimpleNamespace(name_to_rid={living: rid}, rid=g.rid)
    rooms = _export_rooms_from_state(
        g,
        state,
        [c],
        [],
    )
    assert len(rooms) == 1
    poly = [(p.x, p.y) for p in rooms[0].polygon]
    assert abs(polygon_area(poly) - 4 * CELL_AREA) < 1e-6
    assert len(poly) >= 6
