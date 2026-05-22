"""Session cleanup on end/delete."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_end_session_deletes_chat_history():
    client = TestClient(app)
    sid = client.post("/api/v1/sessions").json()["session_id"]
    client.post(
        "/api/v1/chat",
        json={"session_id": sid, "user_message": "三居室 120平"},
    )
    dump = client.get(f"/api/v1/sessions/{sid}").json()
    assert len(dump["messages"]) >= 1

    end = client.post(f"/api/v1/sessions/{sid}/end")
    assert end.status_code == 200
    assert end.json()["cleared"] is True

    assert client.get(f"/api/v1/sessions/{sid}").status_code == 404


def test_shutdown_clears_session_when_requested():
    client = TestClient(app)
    sid = client.post("/api/v1/sessions").json()["session_id"]
    client.post(
        "/api/v1/chat",
        json={"session_id": sid, "user_message": "hello"},
    )

    res = client.post(
        "/api/v1/system/shutdown",
        json={"session_id": sid},
    )
    assert res.status_code == 200
    assert res.json()["session_cleared"] is True
