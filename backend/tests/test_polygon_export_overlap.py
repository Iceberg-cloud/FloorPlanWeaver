"""Ensure grid_search SVG export does not inflate bbox over neighbor cells."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.layout import Point2D, SiteOutline
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem
from app.services.default_semantic_layout import build_default_semantic_plan
from app.services.layout_constraint_builder import build_constraint_plan
from app.services.layout_grid import CELL_SIZE
from app.services.layout_grid_search import run_grid_search_layout
from app.services.layout_grid_search_compiler import _export_rooms_from_state
from app.services.layout_validator import _grid_search_polygon_overlap_errors


def _outline(w: float, h: float) -> SiteOutline:
    return SiteOutline(
        vertices=[
            Point2D(x=0, y=0),
            Point2D(x=w, y=0),
            Point2D(x=w, y=h),
            Point2D(x=0, y=h),
        ],
        entrance_edge=[0, 1],
        total_area_sqm=w * h,
        bounding_box={"width": w, "height": h},
        unit="m",
    )


def test_exported_polygons_do_not_cover_neighbor_cell_centers():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="公寓", target_area_sqm=72, layout_type="两居", orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=22),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=14),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=8),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=5),
            SpaceProgramItem(room_type="阳台", count=1, target_area_sqm=5),
        ],
        adjacency_graph=[],
        drawing_brief="test",
    )
    outline = _outline(10, 8)
    semantic = build_default_semantic_plan(plan)
    cp = build_constraint_plan(plan, semantic, outline)
    state, grid, report = run_grid_search_layout(cp, outline)
    assert state is not None

    rooms = _export_rooms_from_state(grid, state, cp.rooms, outline.vertices)
    assert len(rooms) >= 4
    overlap_errors = _grid_search_polygon_overlap_errors(rooms)
    assert overlap_errors == [], f"export overlap: {overlap_errors}"

    for room in rooms:
        rid = state.name_to_rid.get(room.name)
        if rid is None or len(room.polygon) < 3:
            continue
        poly = [(p.x, p.y) for p in room.polygon]
        from app.services.layout_geometry import point_in_polygon

        for j in range(grid.rows):
            for i in range(grid.cols):
                if not grid.inside[j][i]:
                    continue
                owner = state.rid[j][i]
                if owner == 0 or owner == rid:
                    continue
                cx = grid.origin_x + (i + 0.5) * CELL_SIZE
                cy = grid.origin_y + (j + 0.5) * CELL_SIZE
                assert not point_in_polygon(cx, cy, poly), (
                    f"「{room.name}」导出多边形覆盖了邻居「{state.room_names.get(owner)}」的网格格心"
                )
