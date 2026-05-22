"""Multi-turn chat: working memory accumulates across /chat calls."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.session_repo import InMemorySessionRepository
from app.repositories import session_repo as session_repo_module


def _session_id(client: TestClient) -> str:
    res = client.post("/api/v1/sessions")
    assert res.status_code == 200
    return res.json()["session_id"]


@patch.object(session_repo_module, "create_session_repository", return_value=InMemorySessionRepository())
@patch("app.services.planner_service.LLMClient.generate_json")
def test_chat_multiturn_memory_accumulates(mock_llm, _mock_repo):
    mock_llm.return_value = {"agent_state": "ASK_FOR_MORE"}
    client = TestClient(app)
    sid = _session_id(client)

    r1 = client.post("/api/v1/chat", json={"session_id": sid, "user_message": "三居室"})
    assert r1.status_code == 200
    snap1 = r1.json()["planner"]["collected_snapshot"]
    assert snap1.get("layout_type") == "三居"

    r2 = client.post("/api/v1/chat", json={"session_id": sid, "user_message": "120平米，南向"})
    assert r2.status_code == 200
    assert r2.json()["planner"]["agent_state"] == "FINAL_PLAN"
    assert r2.json()["status"] in ("completed", "draft_ready", "draft_failed")

    sess = client.get(f"/api/v1/sessions/{sid}")
    assert sess.status_code == 200
    assert sess.json()["collected_requirements"]["target_area_sqm"] == 120
