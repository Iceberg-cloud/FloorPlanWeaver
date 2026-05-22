"""Method A vector layout: area coverage ratio and post-process pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.layout import Point2D, SiteOutline
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem
from app.services.default_semantic_layout import build_default_semantic_plan
from app.services.layout_compiler import compile_semantic_layout
from app.services.layout_constraint_builder import build_constraint_plan
from app.services.layout_grid_search import run_grid_search_layout
from app.services.layout_grid_search_compiler import compile_semantic_layout_grid_search
from app.services.layout_metrics import compute_layout_area_metrics


def _plan_two_bed() -> PlannerFinalPlan:
    return PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="住宅",
            target_area_sqm=80,
            layout_type="两居",
            orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=22),
            SpaceProgramItem(room_type="餐厅", count=1, target_area_sqm=10),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=14),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=8),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=5),
            SpaceProgramItem(room_type="阳台", count=1, target_area_sqm=5),
        ],
        adjacency_graph=[],
        circulation={"main_route": "入户→客厅", "secondary_routes": [], "principle": "动静分离"},
        drawing_brief="test",
    )


def _plan_one_bed() -> PlannerFinalPlan:
    return PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="公寓",
            target_area_sqm=55,
            layout_type="一居",
            orientation="南向",
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


def _outline(w: float, h: float, area: float) -> SiteOutline:
    return SiteOutline(
        vertices=[
            Point2D(x=0, y=0),
            Point2D(x=w, y=0),
            Point2D(x=w, y=h),
            Point2D(x=0, y=h),
        ],
        entrance_edge=[0, 1],
        total_area_sqm=area,
        bounding_box={"width": w, "height": h},
        unit="meter",
    )


@pytest.mark.parametrize(
    "plan_fn,outline,label,min_ratio",
    [
        (_plan_two_bed, _outline(10, 8, 80), "两居80㎡", 0.85),
        (_plan_one_bed, _outline(8, 7, 56), "一居56㎡", 0.80),
    ],
)
def test_vector_layout_area_coverage_ratio(plan_fn, outline, label, min_ratio, capsys):
    plan = plan_fn()
    semantic = build_default_semantic_plan(plan)
    layout, notes = compile_semantic_layout_grid_search(semantic, plan, outline)
    metrics = compute_layout_area_metrics(layout, outline)

    print(
        f"[{label}] 规划面积占比: {metrics.area_coverage_ratio:.1%} "
        f"({metrics.planned_area_sqm}㎡ / {metrics.outline_area_sqm}㎡), "
        f"房间数={metrics.room_count}, compile={layout.compile_method}"
    )
    for line in notes:
        if "占比" in line:
            print(f"  note: {line}")

    assert len(layout.rooms) >= 4, f"{label}: too few rooms"
    assert metrics.outline_area_sqm > 0
    assert metrics.area_coverage_ratio >= min_ratio, (
        f"{label}: coverage {metrics.area_coverage_ratio:.1%} < {min_ratio:.0%}"
    )
    assert any("占比" in n for n in notes)


def test_grid_search_report_has_structured_fields():
    plan = _plan_two_bed()
    outline = _outline(10, 8, 80)
    semantic = build_default_semantic_plan(plan)
    cp = build_constraint_plan(plan, semantic, outline)
    state, grid, report = run_grid_search_layout(cp, outline)

    assert state is not None
    assert report.grid_assignment
    assert len(report.grid_assignment) == grid.rows
    assert report.area_coverage_ratio >= 0.85
    assert report.planned_area_sqm > 0
    assert report.explanation
    assert isinstance(report.repair_log, list)


def test_compile_semantic_uses_grid_not_llm_coords():
    plan = _plan_two_bed()
    outline = _outline(10, 8, 80)
    semantic = build_default_semantic_plan(plan)
    for p in semantic.placements:
        p.center_x = 0.99
        p.center_y = 0.99

    layout, _ = compile_semantic_layout(semantic, plan, outline)
    assert layout.compile_method in ("grid_search", "grid")
    metrics = compute_layout_area_metrics(layout, outline)
    assert metrics.area_coverage_ratio >= 0.5


def _plan_three_bed_two_bath() -> PlannerFinalPlan:
    """9-room plan: 2 bathrooms, 2 bedrooms, kitchen, dining, balcony, living."""
    return PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="住宅",
            target_area_sqm=120,
            layout_type="三居",
            orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=24),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=18),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=9),
            SpaceProgramItem(room_type="卫生间", count=2, target_area_sqm=5),
            SpaceProgramItem(room_type="阳台", count=1, target_area_sqm=6),
            SpaceProgramItem(room_type="餐厅", count=1, target_area_sqm=12),
            SpaceProgramItem(room_type="次卧", count=2, target_area_sqm=12),
        ],
        adjacency_graph=[],
        drawing_brief="test",
    )


def test_9room_grid_search_full_coverage():
    """9-room plan must achieve ≥95% grid coverage with no gaps."""
    plan = _plan_three_bed_two_bath()
    outline = _outline(12, 10, 120)
    semantic = build_default_semantic_plan(plan)
    cp = build_constraint_plan(plan, semantic, outline)
    state, grid, report = run_grid_search_layout(cp, outline)

    assert state is not None, "grid search should not return None for 9-room 120㎡"
    assert report.area_coverage_ratio >= 0.95, (
        f"9-room coverage {report.area_coverage_ratio:.1%} < 95%"
    )

    # Verify no unassigned inside cells
    unassigned = sum(
        1 for j in range(grid.rows) for i in range(grid.cols)
        if grid.inside[j][i] and state.rid[j][i] == 0
    )
    assert unassigned == 0, f"{unassigned} unassigned cells remain"

    # Verify all rooms placed (≥ 1 cell each)
    for c in cp.rooms:
        rid = state.name_to_rid.get(c.name)
        assert rid is not None, f"「{c.name}」not assigned a rid"
        n = sum(
            1 for j in range(grid.rows) for i in range(grid.cols)
            if grid.inside[j][i] and state.rid[j][i] == rid
        )
        assert n > 0, f"「{c.name}」has 0 cells"

    # Print area ratio per room
    from app.services.layout_grid import CELL_AREA
    for c in cp.rooms:
        rid = state.name_to_rid[c.name]
        n = sum(
            1 for j in range(grid.rows) for i in range(grid.cols)
            if grid.inside[j][i] and state.rid[j][i] == rid
        )
        area = n * CELL_AREA
        ratio = area / c.target_area_sqm if c.target_area_sqm > 0 else 0
        print(f"  {c.name:12s} {area:6.1f}㎡ / {c.target_area_sqm:.0f}㎡ = {ratio:.0%}")


def test_9room_all_rooms_inside_outline():
    """All room polygons from 9-room export must be within outline bounds."""
    plan = _plan_three_bed_two_bath()
    outline = _outline(12, 10, 120)
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout_grid_search(semantic, plan, outline)

    assert layout.compile_method == "grid_search"
    for rm in layout.rooms:
        for pt in rm.polygon:
            assert -0.1 <= pt.x <= 12.1, f"{rm.name} x={pt.x:.2f} outside [0,12]"
            assert -0.1 <= pt.y <= 10.1, f"{rm.name} y={pt.y:.2f} outside [0,10]"
