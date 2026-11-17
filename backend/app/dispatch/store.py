"""Bandeja del despachador: Cartas derivadas and their ampliaciones in SQLite (SPEC §5.9).

Append-only like the registro de acciones: a Carta is stored once, as derivada, and what the
operador confirms afterwards is added as ampliaciones. Nothing is updated or deleted.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from app.engine.models import Ampliacion, Carta, CartaChange, Line

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cartas (
    call_id TEXT PRIMARY KEY,
    line TEXT NOT NULL,
    derived_at TEXT NOT NULL,
    carta TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ampliaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL REFERENCES cartas (call_id),
    at TEXT NOT NULL,
    action TEXT NOT NULL,
    changes TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ampliaciones_call ON ampliaciones (call_id);
CREATE TRIGGER IF NOT EXISTS cartas_no_update BEFORE UPDATE ON cartas
BEGIN SELECT RAISE(ABORT, 'cartas is append-only'); END;
CREATE TRIGGER IF NOT EXISTS cartas_no_delete BEFORE DELETE ON cartas
BEGIN SELECT RAISE(ABORT, 'cartas is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ampliaciones_no_update BEFORE UPDATE ON ampliaciones
BEGIN SELECT RAISE(ABORT, 'ampliaciones is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ampliaciones_no_delete BEFORE DELETE ON ampliaciones
BEGIN SELECT RAISE(ABORT, 'ampliaciones is append-only'); END;
"""

_CHANGES = TypeAdapter(list[CartaChange])


class DerivedCarta(BaseModel):
    """A Carta as the despachador gets it: as derivada, then its ampliaciones in order."""

    model_config = ConfigDict(frozen=True)

    call_id: str
    line: Line
    derived_at: datetime
    carta: Carta
    ampliaciones: list[Ampliacion]


class DispatchStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def add_carta(self, call_id: str, line: Line, at: datetime, carta: Carta) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO cartas (call_id, line, derived_at, carta) VALUES (?, ?, ?, ?)",
                (call_id, line.value, at.isoformat(), carta.model_dump_json()),
            )

    def add_ampliacion(self, call_id: str, ampliacion: Ampliacion) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO ampliaciones (call_id, at, action, changes) VALUES (?, ?, ?, ?)",
                (
                    call_id,
                    ampliacion.at.isoformat(),
                    ampliacion.action,
                    _CHANGES.dump_json(ampliacion.changes).decode(),
                ),
            )

    def inbox(self) -> list[DerivedCarta]:
        """Every Carta derivada, the most recent first, with its ampliaciones."""
        with self._connect() as conn:
            cartas = conn.execute(
                "SELECT call_id, line, derived_at, carta FROM cartas ORDER BY rowid DESC"
            ).fetchall()
            rows = conn.execute(
                "SELECT call_id, at, action, changes FROM ampliaciones ORDER BY id"
            ).fetchall()
        by_call: dict[str, list[Ampliacion]] = {}
        for call_id, at, action, changes in rows:
            by_call.setdefault(call_id, []).append(
                Ampliacion(
                    at=datetime.fromisoformat(at),
                    action=action,
                    changes=_CHANGES.validate_json(changes),
                )
            )
        return [
            DerivedCarta(
                call_id=call_id,
                line=Line(line),
                derived_at=datetime.fromisoformat(derived_at),
                carta=Carta.model_validate_json(carta),
                ampliaciones=by_call.get(call_id, []),
            )
            for call_id, line, derived_at, carta in cartas
        ]
