import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.layout import SiteOutline, Point2D
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem
from app.services.default_semantic_layout import build_default_semantic_plan
from app.services.layout_constraint_builder import build_constraint_plan, _priority_index
from app.services.layout_grid import GridMap
from app.services.layout_grid_search import run_grid_search_layout
from app.services.layout_grid_search_compiler import compile_semantic_layout_grid_search


def test_placement_priority_order():
    assert _priority_index("阳台") < _priority_index("卫生间")
    assert _priority_index("卫生间") < _priority_index("主卧")
    assert _priority_index("主卧") < _priority_index("次卧")
    assert _priority_index("次卧") < _priority_index("厨房")
    assert _priority_index("厨房") < _priority_index("书房")
    assert _priority_index("书房") < _priority_index("餐厅")
    assert _priority_index("餐厅") < _priority_index("客厅")


def test_grid_search_fills_all_cells():
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
    outline = SiteOutline(
        vertices=[
            Point2D(x=0, y=0), Point2D(x=9, y=0),
            Point2D(x=9, y=8), Point2D(x=0, y=8),
        ],
        entrance_edge=[0, 1],
        total_area_sqm=72,
        bounding_box={"width": 9, "height": 8},
        unit="m",
    )
    semantic = build_default_semantic_plan(plan)
    cp = build_constraint_plan(plan, semantic, outline)
    state, grid, report = run_grid_search_layout(cp, outline)

    assert state is not None
    free = sum(
        1 for j in range(grid.rows) for i in range(grid.cols)
        if grid.inside[j][i] and state.rid[j][i] == 0
    )
    assert free == 0, f"unassigned cells: {free}"
    assert len(report.room_results) >= 4


def test_compile_grid_search_produces_rooms():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="公寓", target_area_sqm=55, layout_type="一居", orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=18),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=12),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=6),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=4),
        ],
        adjacency_graph=[],
        drawing_brief="test",
    )
    outline = SiteOutline(
        vertices=[Point2D(x=0, y=0), Point2D(x=8, y=0), Point2D(x=8, y=7), Point2D(x=0, y=7)],
        entrance_edge=[0, 1],
        total_area_sqm=56,
        bounding_box={"width": 8, "height": 7},
        unit="m",
    )
    semantic = build_default_semantic_plan(plan)
    layout, notes = compile_semantic_layout_grid_search(semantic, plan, outline)
    assert layout.compile_method in ("grid_search", "grid")
    assert len(layout.rooms) >= 3
    assert any("beam" in n or "网格" in n for n in notes)
