from datetime import datetime

from app.schemas.session import SessionState


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._store: dict[str, SessionState] = {}

    def create(self) -> SessionState:
        session = SessionState()
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
