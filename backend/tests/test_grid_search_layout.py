import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.layout import SiteOutline, Point2D
from app.schemas.planner import AdjacencyRule, PlannerFinalPlan, ProjectProfile, SpaceProgramItem
from app.services.default_semantic_layout import build_default_semantic_plan
from app.services.layout_constraint_builder import (
    build_constraint_plan,
    constraint_counts_match_program,
    _priority_index,
)
from app.services.layout_grid import GridMap
from app.services.layout_grid_search import _touches_outline, run_grid_search_layout
from app.services.layout_grid_search_compiler import compile_semantic_layout_grid_search


def test_placement_priority_order():
    assert _priority_index("阳台") < _priority_index("卫生间")
    assert _priority_index("卫生间") < _priority_index("主卧")
    assert _priority_index("主卧") < _priority_index("次卧")
    assert _priority_index("次卧") < _priority_index("餐厅")
    assert _priority_index("餐厅") < _priority_index("厨房")
    assert _priority_index("厨房") < _priority_index("书房")
    assert _priority_index("书房") < _priority_index("客厅")


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


def test_kitchen_must_touch_outline_and_matches_program():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="公寓", target_area_sqm=72, layout_type="两居", orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=22),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=14),
            SpaceProgramItem(room_type="次卧", count=1, target_area_sqm=10),
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
    assert constraint_counts_match_program(cp, plan)

    kitchen = next(r for r in cp.rooms if r.room_type == "厨房")
    assert kitchen.must_touch_outline is True
    assert kitchen.target_area_sqm == 8.0

    state, grid, report = run_grid_search_layout(cp, outline)
    assert state is not None
    kid = state.name_to_rid["厨房"]
    kitchen_cells = [
        (i, j)
        for j in range(grid.rows)
        for i in range(grid.cols)
        if state.rid[j][i] == kid
    ]
    assert kitchen_cells
    assert any(_touches_outline(grid, i, j) for i, j in kitchen_cells)

    by_type: dict[str, int] = {}
    for r in report.room_results:
        by_type[r.room_type] = by_type.get(r.room_type, 0) + 1
    for item in plan.space_program:
        assert by_type.get(item.room_type, 0) >= max(1, item.count)


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


def test_default_semantic_kitchen_dining_must_adjacency():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="公寓", target_area_sqm=80, layout_type="两居", orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=22),
            SpaceProgramItem(room_type="餐厅", count=1, target_area_sqm=10),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=8),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=14),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=5),
        ],
        adjacency_graph=[],
        drawing_brief="test",
    )
    semantic = build_default_semantic_plan(plan)
    must_pairs = {
        (a.a, a.b) if a.a <= a.b else (a.b, a.a)
        for a in semantic.adjacency_intent
        if a.strength == "must"
    }
    assert ("厨房", "餐厅") in must_pairs


def test_plan_adjacency_graph_merged_into_constraints():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="公寓", target_area_sqm=80, layout_type="两居", orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=22),
            SpaceProgramItem(room_type="餐厅", count=1, target_area_sqm=10),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=8),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=14),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=5),
        ],
        adjacency_graph=[
            AdjacencyRule(source="厨房", target="餐厅", relation="required", description="备餐"),
        ],
        drawing_brief="test",
    )
    outline = SiteOutline(
        vertices=[Point2D(x=0, y=0), Point2D(x=9, y=0), Point2D(x=9, y=8), Point2D(x=0, y=8)],
        entrance_edge=[0, 1],
        total_area_sqm=72,
        bounding_box={"width": 9, "height": 8},
        unit="m",
    )
    semantic = build_default_semantic_plan(plan)
    cp = build_constraint_plan(plan, semantic, outline)
    kitchen = next(r for r in cp.rooms if r.room_type == "厨房")
    assert "餐厅" in kitchen.adjacency_required
