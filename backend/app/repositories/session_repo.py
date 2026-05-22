import os
from datetime import datetime
from pathlib import Path

from app.core.config import BACKEND_DIR, settings
from app.schemas.session import SessionState


def _new_session() -> SessionState:
    from app.core.config import settings

    session = SessionState()
    dm = settings.default_draw_mode
    if dm in ("vector", "multimodal", "both"):
        session.draw_method = dm
    return session


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._store: dict[str, SessionState] = {}

    def create(self) -> SessionState:
        session = _new_session()
        self._store[session.session_id] = session
        return session

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._store:
            raise KeyError(f"Session not found: {session_id}")
        return self._store[session_id]

    def save(self, session: SessionState) -> SessionState:
        session.updated_at = datetime.utcnow()
        self._store[session.session_id] = session
        return session

    def delete(self, session_id: str) -> bool:
        if session_id in self._store:
            del self._store[session_id]
            return True
        return False


def create_session_repository():
    """Pytest uses in-memory; default runtime uses SQLite (P0 persistence)."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return InMemorySessionRepository()
    if settings.session_store == "memory":
        return InMemorySessionRepository()
    from app.repositories.sqlite_session_repo import SqliteSessionRepository

    return SqliteSessionRepository(settings.session_db_path)
