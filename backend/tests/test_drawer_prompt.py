import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.prompts import build_drawer_image_prompt
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem


def test_drawer_prompt_forbids_dimensions_and_long_text():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="住宅", target_area_sqm=120, layout_type="三居", orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=26),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=18),
        ],
        adjacency_graph=[],
        drawing_brief="这是一段很长的设计说明，不应出现在出图提示中要求画在图上。",
    )
    prompt = build_drawer_image_prompt(plan)
    assert "禁止" in prompt
    assert "不标注房间名称" in prompt
    assert "客厅" in prompt and "主卧" in prompt
    assert "120" not in prompt
    assert "26" not in prompt and "18" not in prompt
    assert plan.drawing_brief not in prompt
    assert "动线描述" in prompt or "设计说明" in prompt
