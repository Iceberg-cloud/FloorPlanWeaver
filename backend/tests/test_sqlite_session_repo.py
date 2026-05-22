import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.repositories.sqlite_session_repo import SqliteSessionRepository
from app.schemas.session import ChatMessage


def test_sqlite_persists_messages_and_memory(tmp_path):
    db = tmp_path / "sessions.db"
    repo1 = SqliteSessionRepository(db)
    session = repo1.create()
    session.messages.append(ChatMessage(role="user", content="三居 120平"))
    session.collected_requirements = {"layout_type": "三居", "target_area_sqm": 120}
    repo1.save(session)

    repo2 = SqliteSessionRepository(db)
    loaded = repo2.get(session.session_id)
    assert loaded.collected_requirements["layout_type"] == "三居"
    assert len(loaded.messages) == 1
    assert loaded.messages[0].content == "三居 120平"
