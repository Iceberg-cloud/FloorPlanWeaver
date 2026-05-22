"""SQLite-backed session persistence (stdlib sqlite3)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.repositories.session_repo import _new_session
from app.schemas.session import SessionState


class SqliteSessionRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def create(self) -> SessionState:
        session = _new_session()
        self.save(session)
        return session

    def get(self, session_id: str) -> SessionState:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Session not found: {session_id}")
        return SessionState.model_validate_json(row["state_json"])

    def save(self, session: SessionState) -> SessionState:
        session.updated_at = datetime.utcnow()
        payload = session.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (session.session_id, payload, session.updated_at.isoformat()),
            )
            conn.commit()
        return session

    def delete(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cur.rowcount > 0
