"""Registro de acciones: append-only SQLite table of everything the operador did (SPEC §5.10).

The repository exposes no update or delete, and the table refuses them with triggers.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    at TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    before TEXT,
    after TEXT,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS action_log_call ON action_log (call_id);
CREATE TRIGGER IF NOT EXISTS action_log_no_update BEFORE UPDATE ON action_log
BEGIN SELECT RAISE(ABORT, 'action_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS action_log_no_delete BEFORE DELETE ON action_log
BEGIN SELECT RAISE(ABORT, 'action_log is append-only'); END;
"""


class ActionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    call_id: str
    at: datetime
    action: str
    target: str | None = None
    before: str | None = None
    after: str | None = None
    reason: str | None = None


class ActionLog:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def append(self, record: ActionRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO action_log (call_id, at, action, target, before, after, reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.call_id,
                    record.at.isoformat(),
                    record.action,
                    record.target,
                    record.before,
                    record.after,
                    record.reason,
                ),
            )

    def for_call(self, call_id: str) -> list[ActionRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT call_id, at, action, target, before, after, reason "
                "FROM action_log WHERE call_id = ? ORDER BY id",
                (call_id,),
            ).fetchall()
        return [
            ActionRecord(
                call_id=r[0],
                at=datetime.fromisoformat(r[1]),
                action=r[2],
                target=r[3],
                before=r[4],
                after=r[5],
                reason=r[6],
            )
            for r in rows
        ]
