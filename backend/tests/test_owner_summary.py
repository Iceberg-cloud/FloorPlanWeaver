import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem


def test_plan_total_area():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(building_type="公寓", target_area_sqm=90, layout_type="三居", orientation="南向"),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=20),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=14),
        ],
        adjacency_graph=[], drawing_brief="test",
    )
    total = sum(item.target_area_sqm or 0 for item in plan.space_program)
    assert total == 34
