"""Trazas of every lectura in SQLite, append-only like the registro de acciones (SPEC §5.11).

They outlive the llamada: once it is closed its trazas can still be read, and the métricas
count them together with the registro.
"""

import sqlite3
from pathlib import Path

from app.trace.models import ReadingTrace

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reading_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    at TEXT NOT NULL,
    trace TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS reading_traces_call ON reading_traces (call_id);
CREATE TRIGGER IF NOT EXISTS reading_traces_no_update BEFORE UPDATE ON reading_traces
BEGIN SELECT RAISE(ABORT, 'reading_traces is append-only'); END;
CREATE TRIGGER IF NOT EXISTS reading_traces_no_delete BEFORE DELETE ON reading_traces
BEGIN SELECT RAISE(ABORT, 'reading_traces is append-only'); END;
"""


class TraceStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def append(self, trace: ReadingTrace) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reading_traces (call_id, idx, at, trace) VALUES (?, ?, ?, ?)",
                (trace.call_id, trace.index, trace.at.isoformat(), trace.model_dump_json()),
            )

    def for_call(self, call_id: str) -> list[ReadingTrace]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT trace FROM reading_traces WHERE call_id = ? ORDER BY id", (call_id,)
            ).fetchall()
        return [ReadingTrace.model_validate_json(r[0]) for r in rows]

    def all(self) -> list[ReadingTrace]:
        with self._connect() as conn:
            rows = conn.execute("SELECT trace FROM reading_traces ORDER BY id").fetchall()
        return [ReadingTrace.model_validate_json(r[0]) for r in rows]
