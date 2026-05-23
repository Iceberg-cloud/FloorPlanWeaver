import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.layout import Point2D, SiteOutline
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem
from app.services.requirement_memory import (
    align_memory_with_outline,
    outline_reminder_notices,
    reconcile_final_plan,
)


def _outline(area: float) -> SiteOutline:
    w = 10.0
    h = area / w
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
        unit="m",
    )


def test_align_memory_prefers_outline_over_user_area():
    mem = {"layout_type": "三居", "target_area_sqm": 140}
    outline = _outline(96.0)
    aligned, notices = align_memory_with_outline(mem, outline)
    assert aligned["target_area_sqm"] == 96.0
    assert any("外轮廓" in n for n in notices)
    assert any("140" in n for n in notices)


def test_align_memory_no_notice_when_areas_match():
    mem = {"target_area_sqm": 120}
    outline = _outline(120.0)
    _, notices = align_memory_with_outline(mem, outline)
    assert notices == []


def test_reconcile_final_plan_uses_outline_area():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="住宅",
            target_area_sqm=140,
            layout_type="三居",
            orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=40),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=20),
        ],
        adjacency_graph=[],
        drawing_brief="test",
    )
    out = reconcile_final_plan(plan, {"target_area_sqm": 140}, outline=_outline(96.0))
    assert out.project_profile.target_area_sqm == 96.0
    planned = sum(p.target_area_sqm * p.count for p in out.space_program)
    assert planned < 140


def test_outline_reminder_when_missing():
    assert outline_reminder_notices(False)
    assert outline_reminder_notices(True) == []
