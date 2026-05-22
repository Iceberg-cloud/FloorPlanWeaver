"""API integration: frontend /chat contract with partial LLM planner payloads."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def _session_id(client: TestClient) -> str:
    res = client.post("/api/v1/sessions")
    assert res.status_code == 200
    return res.json()["session_id"]


@patch("app.services.planner_service.LLMClient.generate_json")
def test_chat_partial_ask_for_more_llm(mock_llm):
    mock_llm.return_value = {"agent_state": "ASK_FOR_MORE"}
    client = TestClient(app)
    sid = _session_id(client)

    res = client.post(
        "/api/v1/chat",
        json={"session_id": sid, "user_message": "我想做一套三居室"},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "collecting"
    assert body["planner"]["agent_state"] == "ASK_FOR_MORE"
    assert isinstance(body["planner"]["missing_fields"], list)
    assert len(body["planner"]["missing_fields"]) > 0
    assert isinstance(body["planner"]["follow_up_questions"], list)
    assert len(body["planner"]["follow_up_questions"]) > 0
    assert body["runtime"]["planner"]["error"] in (None, "")


@patch("app.services.planner_service.LLMClient.generate_json")
def test_chat_nested_partial_ask_for_more_llm(mock_llm):
    mock_llm.return_value = {"planner": {"agent_state": "ASK_FOR_MORE"}}
    client = TestClient(app)
    sid = _session_id(client)

    res = client.post(
        "/api/v1/chat",
        json={"session_id": sid, "user_message": "120平米"},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["planner"]["agent_state"] == "ASK_FOR_MORE"
    assert len(body["planner"]["follow_up_questions"]) > 0


@patch("app.services.planner_service.LLMClient.generate_json")
def test_chat_partial_final_plan_llm_falls_back(mock_llm):
    mock_llm.return_value = {"agent_state": "FINAL_PLAN"}
    client = TestClient(app)
    sid = _session_id(client)

    res = client.post(
        "/api/v1/chat",
        json={"session_id": sid, "user_message": "三居 120平 南向"},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    # Incomplete FINAL_PLAN should coerce to ASK or complete plan, never 500
    assert body["planner"]["agent_state"] in ("ASK_FOR_MORE", "FINAL_PLAN")
    assert body["runtime"]["planner"]["error"] in (None, "")


def test_health():
    client = TestClient(app)
    assert client.get("/api/v1/health").json() == {"status": "ok"}
