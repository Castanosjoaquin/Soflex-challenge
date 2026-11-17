"""Parse the dataset CSV into catalog cases and persist them in SQLite."""

import csv
import json
import sqlite3
from pathlib import Path

from app.catalog.models import CatalogCase, Category, Priority


def _split_questions(raw: str) -> list[str]:
    return [q.strip() for q in raw.split("|") if q.strip()]


def parse_dataset(path: Path) -> list[CatalogCase]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [
        CatalogCase(
            id=row["id_registro"],
            timestamp=row["timestamp_llamada"],
            source=row["origen_reporte"],
            category=Category(row["categoria"]),
            subcategory=row["subcategoria"],
            priority=Priority(row["prioridad_sugerida"]),
            transcript=row["transcripcion_cruda"],
            street=row["calle_detectada"],
            street_number=row["altura_detectada"],
            intersection=row["interseccion_detectada"],
            neighborhood=row["barrio_comuna"],
            mandatory_questions=_split_questions(row["preguntas_protocolo_mandatorias"]),
            answered_questions=_split_questions(row["preguntas_respondidas_en_relato"]),
            pending_questions=_split_questions(row["preguntas_pendientes"]),
            prearrival_instructions=row["instrucciones_prearribo"],
            detected_risks=row["riesgos_detectados"],
            recommended_resources=row["recursos_recomendados_despacho"],
            dispatch_notes=row["notas_operativas_despacho"],
        )
        for row in rows
    ]


def seed_database(db_path: Path, cases: list[CatalogCase]) -> None:
    """(Re)create the catalog table. Idempotent: safe to run on every startup."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS catalog_cases")
        conn.execute(
            "CREATE TABLE catalog_cases (id TEXT PRIMARY KEY, category TEXT NOT NULL, "
            "priority TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO catalog_cases VALUES (?, ?, ?, ?)",
            [(c.id, c.category.value, c.priority.value, c.model_dump_json()) for c in cases],
        )


def load_cases(db_path: Path) -> list[CatalogCase]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT payload FROM catalog_cases ORDER BY id").fetchall()
    return [CatalogCase.model_validate(json.loads(payload)) for (payload,) in rows]
