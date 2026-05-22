from app.schemas.planner import PlannerAskForMore
from app.services.planner_service import _coerce_planner_payload, _parse_planner_llm_payload


def test_coerce_ask_for_more_fills_missing_fields():
    payload = {"agent_state": "ASK_FOR_MORE"}
    out = _coerce_planner_payload(payload, {}, "三居 120平")

    assert out["agent_state"] == "ASK_FOR_MORE"
    assert isinstance(out["missing_fields"], list)
    assert len(out["missing_fields"]) > 0
    assert isinstance(out["follow_up_questions"], list)
    assert len(out["follow_up_questions"]) > 0
    assert isinstance(out["collected_snapshot"], dict)


def test_coerce_final_plan_from_rule_when_llm_empty():
    payload = {"agent_state": "FINAL_PLAN"}
    collected = {
        "building_type": "住宅",
        "target_area_sqm": 120,
        "layout_type": "三居",
        "room_program": [
            {"room_type": "客厅", "count": 1, "target_area_sqm": 24},
            {"room_type": "主卧", "count": 1, "target_area_sqm": 18},
        ],
        "orientation": "南向优先",
    }
    out = _coerce_planner_payload(payload, collected, "按上述需求出方案")

    assert out["agent_state"] == "FINAL_PLAN"
    assert out.get("space_program")
    assert out.get("drawing_brief")
    assert out.get("project_profile")


def test_coerce_final_plan_downgrades_to_ask_when_incomplete():
    payload = {"agent_state": "FINAL_PLAN"}
    out = _coerce_planner_payload(payload, {}, "你好")

    assert out["agent_state"] == "ASK_FOR_MORE"
    assert out.get("missing_fields")


def test_parse_raw_ask_for_more_without_coerce_fields():
    result = _parse_planner_llm_payload({"agent_state": "ASK_FOR_MORE"}, {}, "你好")
    assert isinstance(result, PlannerAskForMore)
    assert len(result.missing_fields) > 0
    assert len(result.follow_up_questions) > 0


def test_parse_normalizes_agent_state_variants():
    result = _parse_planner_llm_payload({"agent_state": "ask for more"}, {}, "你好")
    assert isinstance(result, PlannerAskForMore)


def test_parse_nested_planner_key():
    result = _parse_planner_llm_payload(
        {"planner": {"agent_state": "ASK_FOR_MORE"}}, {}, "三居",
    )
    assert isinstance(result, PlannerAskForMore)
    assert len(result.follow_up_questions) > 0
