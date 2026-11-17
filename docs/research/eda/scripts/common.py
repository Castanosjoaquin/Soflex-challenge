"""Utilidades compartidas para el EDA del dataset del challenge Soflex."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data" / "dataset_challenge_soflex.csv"
EDA_DIR = Path(__file__).resolve().parents[1]
FIG_DIR = EDA_DIR / "figures"
OUT_DIR = EDA_DIR / "scripts" / "_out"
FIG_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

CAT_ORDER = [
    "INCENDIO_RESCATE",
    "ACCIDENTE_VIAL",
    "EMERGENCIA_MEDICA",
    "DEFENSA_CIVIL",
    "SERVICIOS_PUBLICOS",
    "CONVIVENCIA_SEGURIDAD",
]
PRIO_ORDER = ["P1", "P2", "P3", "P4"]
PRIO_COLORS = {"P1": "#c0392b", "P2": "#e67e22", "P3": "#2e86c1", "P4": "#7f8c8d"}

STOPWORDS = set(
    """a al ante con contra de del desde el en entre hacia hasta la las lo los para por
    que se sin sobre su sus un una unos unas y o es esta está están hay le les me mi mis
    ya no si sí muy más pero como ha han fue son ser al the tiene tienen todo toda
    ¿ ? ! ¡ . , ( ) eso esa ese este esto estoy""".split()
)


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df["ts"] = pd.to_datetime(df["timestamp_llamada"])
    df["n"] = df["id_registro"].str[-3:].astype(int)
    return df


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


ABBREV = [
    (r"\bav\.?\s", "avenida "),
    (r"\bgral\.?\s", "general "),
    (r"\bdr\.?\s", "doctor "),
    (r"\bjuan b\.?\s", "juan bautista "),
]


def norm(s: str) -> str:
    """Normaliza: minúsculas, sin acentos, expande abreviaturas, sin puntuación."""
    s = strip_accents(str(s).lower())
    for pat, rep in ABBREV:
        s = re.sub(pat, rep, s + " ").strip()
    s = re.sub(r"[^\w\s/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str, stem: int = 5) -> list[str]:
    """Tokens de contenido normalizados y 'stemmeados' por prefijo (heurística barata)."""
    out = []
    for t in norm(s).split():
        if t in STOPWORDS or strip_accents(t) in {strip_accents(w) for w in STOPWORDS}:
            continue
        if len(t) <= 2 and not t.isdigit():
            continue
        out.append(t[:stem] if stem else t)
    return out


def split_pipe(s) -> list[str]:
    if pd.isna(s) or not str(s).strip():
        return []
    return [p.strip() for p in str(s).split("|") if p.strip()]


def split_answer(item: str) -> tuple[str, str]:
    """'¿Pregunta? (respuesta)' -> (pregunta, respuesta)."""
    m = re.match(r"^(.*?\?)\s*\((.*)\)\s*$", item)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return item.strip(), ""


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def caller_text(transcript: str) -> str:
    parts = re.split(r"Llamante:", transcript, maxsplit=1)
    return parts[1] if len(parts) > 1 else transcript


def md_table(df: pd.DataFrame, index: bool = True) -> str:
    return df.to_markdown(index=index)
