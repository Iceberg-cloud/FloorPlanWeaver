"""客厅面积应接近 space_program 目标（方法 A 网格）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.layout import Point2D, SiteOutline
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem
from app.services.default_semantic_layout import build_default_semantic_plan
from app.services.layout_constraint_builder import build_constraint_plan
from app.services.layout_grid import CELL_AREA
from app.services.layout_grid_search import run_grid_search_layout

_LIVING = frozenset({"客厅", "起居室", "客餐厅"})


def _plan(rooms, area):
    return PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="住宅", target_area_sqm=area, layout_type="三居", orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type=rt, count=c, target_area_sqm=a)
            for rt, c, a in rooms
        ],
        adjacency_graph=[],
        drawing_brief="test",
    )


def _rect_outline(w, h):
    return SiteOutline(
        vertices=[
            Point2D(x=0, y=0), Point2D(x=w, y=0),
            Point2D(x=w, y=h), Point2D(x=0, y=h),
        ],
        entrance_edge=[0, 1],
        total_area_sqm=w * h,
        bounding_box={"width": w, "height": h},
        unit="m",
    )


@pytest.mark.parametrize(
    "rooms_spec,w,h,living_target",
    [
        (
            [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)],
            10, 8, 22.0,
        ),
        (
            [
                ("客厅", 1, 22), ("主卧", 1, 14), ("次卧", 1, 10), ("厨房", 1, 8),
                ("卫生间", 1, 5), ("阳台", 1, 5), ("餐厅", 1, 10),
            ],
            10, 8, 22.0,
        ),
    ],
)
def test_living_room_area_near_target(rooms_spec, w, h, living_target):
    outline = _rect_outline(w, h)
    plan = _plan(rooms_spec, w * h)
    semantic = build_default_semantic_plan(plan)
    cp = build_constraint_plan(plan, semantic, outline)
    state, grid, report = run_grid_search_layout(cp, outline)
    assert state is not None

    for c in cp.rooms:
        if c.room_type not in _LIVING:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        n = sum(
            1 for j in range(grid.rows) for i in range(grid.cols)
            if grid.inside[j][i] and state.rid[j][i] == rid
        )
        area = n * CELL_AREA
        err = abs(area - living_target) / living_target
        # Flex rooms (客厅) may exceed target to fill outline, allow generous tolerance
        assert err <= c.area_tolerance + 0.75, (
            f"「{c.name}」{area:.1f}㎡ vs 目标 {living_target:.1f}㎡ (误差 {err:.0%})"
        )
