"""Build data/streets.json, the official street list of CABA, from BA Data "Calles" (CC-BY).

    cd backend && uv run python ../scripts/build_streets.py                 # downloads it
    cd backend && uv run python ../scripts/build_streets.py callejero.csv   # or a local copy

Only the standard library (Python 3.12), no backend dependencies. The output is committed, so
neither the app nor the Docker build touch the network (SPEC §5.5).

From the ~32.000 segments of the callejero we keep one entry per official name:

- ``name``: the name as the sala writes it ("AV. RAUL SCALABRINI ORTIZ", "JORGE LUIS BORGES").
- ``short``: the surname alone, for people's names ("SCALABRINI ORTIZ", "BORGES"), or null.
- ``kind``: the most common ``tipo_c`` of its segments ("avenida", "calle", "pasaje"…).
- ``previous``: its previous names (``nomanter``), cleaned ("SERRANO", "CANNING").
- ``alturas``: the lowest and highest door number of its segments, or null when unnumbered. It tells
  apart a street that was renamed only in part ("SERRANO" 1-1600, "JORGE LUIS BORGES" 1601-2500).
- ``length_m``: its total length, to rank equally good candidates by how well known they are.

Unnamed segments ("SIN NOMBRE OFICIAL (ALT. EDISON 2700)") are left out: nobody calls them that.
"""

import csv
import io
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SOURCE_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "jefatura-de-gabinete-de-ministros/calles/callejero.csv"
)
DATASET_PAGE = "https://data.buenosaires.gob.ar/dataset/calles"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "streets.json"

_ALTURA_FIELDS = ("alt_izqini", "alt_izqfin", "alt_derini", "alt_derfin")
_UNNAMED = re.compile(r"^SIN NOMBRE|\(ALT(?:\.|URA)", re.IGNORECASE)
_AVENUE = re.compile(r"\bAV\b\.?", re.IGNORECASE)
_PARENTHETICAL = re.compile(r"\([^)]*\)?")


@dataclass
class _Street:
    short: str | None = None
    kinds: Counter[str] = field(default_factory=Counter)
    previous: set[str] = field(default_factory=set)
    alturas: list[int] = field(default_factory=list)
    length_m: float = 0.0


def display_name(official: str) -> str:
    """The name as the sala writes it.

    "SCALABRINI ORTIZ, RAUL AV." → "AV. RAUL SCALABRINI ORTIZ"; "CANTILO, INT." → "INT. CANTILO".
    """
    name = " ".join(official.split())
    is_avenue = bool(_AVENUE.search(name))
    name = _AVENUE.sub(" ", name)
    if "," in name:
        # "DICKMAN, ADOLFO, DR." → "DR. ADOLFO DICKMAN"
        surname, *given = (part.strip() for part in name.split(","))
        name = " ".join([*reversed(given), surname])
    name = " ".join(name.split()).strip(" ,")
    return f"AV. {name}" if is_avenue else name


def short_name(official: str) -> str | None:
    """How people call a street named after someone: "SCALABRINI ORTIZ, RAUL AV." → "SCALABRINI
    ORTIZ"."""
    if "," not in official:
        return None
    surname = " ".join(_AVENUE.sub(" ", official.split(",", 1)[0]).split())
    return surname or None


def previous_names(raw: str) -> set[str]:
    """Previous names, cleaned and split.

    "17 DE OCTUBRE - JUSTO, JUAN B., Av. y parciales:" → {"17 DE OCTUBRE", "AV. JUAN B. JUSTO"}.
    """
    text = _PARENTHETICAL.sub(" ", raw)
    text = re.sub(r"\by\s+parciales\s*:?", " ", text, flags=re.IGNORECASE)
    names = set()
    for part in re.split(r"\s*-\s*", text):
        part = part.strip(" ,.:;")
        if len(part) >= 3 and not _UNNAMED.search(part):
            names.add(display_name(part.upper()))
    return names


def build(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    streets: dict[str, _Street] = defaultdict(_Street)
    for row in rows:
        official = row["nomoficial"].strip()
        if not official or _UNNAMED.search(official):
            continue
        street = streets[display_name(official)]
        street.short = street.short or short_name(official)
        if row["tipo_c"].strip():
            street.kinds[row["tipo_c"].strip().lower()] += 1
        street.previous |= previous_names(row["nomanter"])
        street.alturas += [n for f in _ALTURA_FIELDS if (n := int(float(row[f] or 0))) > 0]
        street.length_m += float(row["long"] or 0)

    entries = []
    for name, street in sorted(streets.items()):
        entries.append(
            {
                "name": name,
                "short": street.short,
                "kind": street.kinds.most_common(1)[0][0] if street.kinds else "calle",
                "previous": sorted(street.previous - {name}),
                "alturas": [min(street.alturas), max(street.alturas)] if street.alturas else None,
                "length_m": round(street.length_m),
            }
        )
    return entries


def _read(source: str | None) -> str:
    if source:
        return Path(source).read_text(encoding="utf-8-sig")
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
        return response.read().decode("utf-8-sig")


def main() -> None:
    rows = list(csv.DictReader(io.StringIO(_read(sys.argv[1] if len(sys.argv) > 1 else None))))
    entries = build(rows)
    header = {
        "source": f'BA Data, "Calles" ({DATASET_PAGE})',
        "license": "CC-BY: Gobierno de la Ciudad de Buenos Aires",
        "url": SOURCE_URL,
        "built_at": datetime.now(UTC).date().isoformat(),
        "segments": len(rows),
    }
    # One street per line keeps the committed file diffable.
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    head = json.dumps(header, ensure_ascii=False, indent=2)[:-2]
    OUTPUT.write_text(f'{head},\n  "streets": [\n    ' + ",\n    ".join(lines) + "\n  ]\n}\n")
    print(f"{len(entries)} calles → {OUTPUT}")


if __name__ == "__main__":
    main()
