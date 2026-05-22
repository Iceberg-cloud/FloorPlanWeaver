import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.planner_agent import PlannerAgent
from app.services.planner_service import PlannerService


def test_ready_for_plan_after_layout_only():
    agent = PlannerAgent()
    out = agent.run("我想做一套三居室", collected={}, ask_count=0)
    assert out.agent_state == "FINAL_PLAN"
    assert out.space_program


def test_force_finalize_on_second_ask_round():
    agent = PlannerAgent()
    out = agent.run("帮我设计户型", collected={}, ask_count=1, force_finalize=True)
    assert out.agent_state == "FINAL_PLAN"


def test_vague_first_message_asks_once():
    agent = PlannerAgent()
    out = agent.run("设计房子", collected={}, ask_count=0)
    assert out.agent_state == "ASK_FOR_MORE"
    assert len(out.follow_up_questions) <= 2


def test_at_most_two_questions():
    agent = PlannerAgent()
    out = agent.run("设计房子", collected={}, ask_count=0)
    assert len(out.follow_up_questions) <= 2


def test_service_force_after_max_ask():
    svc = PlannerService()
    result = svc.generate(
        user_message="随便看看",
        collected_requirements={},
        ask_count=2,
        force_finalize=True,
    )
    assert result.output.agent_state == "FINAL_PLAN"
