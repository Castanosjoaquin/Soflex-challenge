"""Variantes ruidosas of the dataset llamadas, for the evaluación (SPEC §8).

The 30 relatos of the dataset are clean: no ASR noise, no hesitation, every one says where it is
(EDA §7). Each variante takes one llamada and applies **one** kind of noise to the llamante's
turnos (the operador's stay as they are), so the degradación can be read noise by noise:

- ``muletillas``: "eh,", "este…", "o sea," and others the normalizador does not know ("bueno,").
- ``numeros_en_palabras``: every number said in words ("1540" → "mil quinientos cuarenta").
- ``typos_asr``: what an ASR gets wrong by sound: b/v, ll/y, c/s/z, h muda, no tildes.
- ``autocorreccion``: a wrong ubicación first, then "no, perdón," and the right one.
- ``sin_av``: "Av." and "Avenida" left out, as people say it.
- ``minusculas``: the whole turno in lowercase, as most ASR output comes (review note on #13).
- ``sin_direccion``: the ubicación cut out of the relato: nothing to locate.

The two that touch the ubicación find it with the Lector por reglas on the original turno, so they
only apply where the rules read a ubicación; a variante whose noise found nothing to change says
so (``applied: false``) and still counts, as a copy of the original.

Everything is seeded: the same seed, case and kind give the same variante, and the files in
``data/eval/noisy/`` are the output of ``uv run python -m app.eval.noise``.
"""

import json
import re
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path
from random import Random

from pydantic import BaseModel, ConfigDict

from app.catalog.loader import parse_dataset
from app.catalog.models import CatalogCase
from app.config import REPO_ROOT
from app.readers.rules.location import read_turn_location
from app.transcript.models import ParsedTurn, Speaker, Turn
from app.transcript.parser import parse_transcript

SEED = 13
NOISY_DIR = REPO_ROOT / "data" / "eval" / "noisy"


class NoiseKind(StrEnum):
    MULETILLAS = "muletillas"
    NUMEROS_EN_PALABRAS = "numeros_en_palabras"
    TYPOS_ASR = "typos_asr"
    AUTOCORRECCION = "autocorreccion"
    SIN_AV = "sin_av"
    MINUSCULAS = "minusculas"
    SIN_DIRECCION = "sin_direccion"

    @property
    def keeps_location(self) -> bool:
        """Whether the variante still says the ubicación of the dataset row."""
        return self is not NoiseKind.SIN_DIRECCION


class Variant(BaseModel):
    """One llamada of the dataset with one kind of noise on the llamante's turnos."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    kind: NoiseKind
    applied: bool
    turns: list[ParsedTurn]


# --- Text noise ----------------------------------------------------------------------------------

_FILLERS = ("eh,", "este…", "o sea,", "mmm,", "viste,", "bueno,", "tipo,")
_FILLER_RATE = 0.12


def add_fillers(text: str, rng: Random) -> str:
    """Muletillas before some words (never the first one), at least one."""
    words = text.split(" ")
    if len(words) < 2:
        return text
    slots = [i for i in range(1, len(words)) if rng.random() < _FILLER_RATE]
    if not slots:
        slots = [rng.randrange(1, len(words))]
    out: list[str] = []
    for i, word in enumerate(words):
        if i in slots:
            out.append(rng.choice(_FILLERS))
        out.append(word)
    return " ".join(out)


_UNITS = ("cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve")
_TEENS = (
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
    "veinte",
    "veintiuno",
    "veintidós",
    "veintitrés",
    "veinticuatro",
    "veinticinco",
    "veintiséis",
    "veintisiete",
    "veintiocho",
    "veintinueve",
)
_TENS = ("", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa")
_HUNDREDS = (
    "",
    "ciento",
    "doscientos",
    "trescientos",
    "cuatrocientos",
    "quinientos",
    "seiscientos",
    "setecientos",
    "ochocientos",
    "novecientos",
)
MAX_NUMBER = 99_999


def _below_hundred(n: int) -> str:
    if n < 10:
        return _UNITS[n]
    if n < 30:
        return _TEENS[n - 10]
    tens, units = divmod(n, 10)
    return _TENS[tens] if units == 0 else f"{_TENS[tens]} y {_UNITS[units]}"


def _below_thousand(n: int) -> str:
    if n == 100:
        return "cien"
    hundreds, rest = divmod(n, 100)
    if hundreds == 0:
        return _below_hundred(rest)
    return _HUNDREDS[hundreds] if rest == 0 else f"{_HUNDREDS[hundreds]} {_below_hundred(rest)}"


def number_in_words(n: int) -> str:
    """0 to 99999 in Spanish words, as said: 1540 → "mil quinientos cuarenta"."""
    if not 0 <= n <= MAX_NUMBER:
        raise ValueError(f"{n} is out of 0..{MAX_NUMBER}")
    if n < 1000:
        return _below_thousand(n)
    thousands, rest = divmod(n, 1000)
    # Before "mil", "uno" drops its last vowel: "veintiún mil", "treinta y un mil".
    head = "mil" if thousands == 1 else f"{_below_thousand(thousands)} mil"
    head = re.sub(r"veintiuno mil$", "veintiún mil", head)
    head = re.sub(r"\buno mil$", "un mil", head)
    return head if rest == 0 else f"{head} {_below_thousand(rest)}"


# A whole number: not part of a decimal ("Km 4.5"), a time ("16:35") or a code ("S/N").
_NUMBER = re.compile(r"(?<![\d.,:/])\d{1,5}(?![\d.,:/]\d|\d)")


def numbers_in_words(text: str) -> str:
    return _NUMBER.sub(lambda m: number_in_words(int(m.group())), text)


# Errors by sound, as an ASR makes them on Rioplatense Spanish.
_SOUND_SWAPS = (
    ("v", "b"),
    ("b", "v"),
    ("ll", "y"),
    ("y", "ll"),
    ("ce", "se"),
    ("ci", "si"),
    ("z", "s"),
    ("qu", "k"),
)
_ACCENTS = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")
_TYPO_RATE = 0.2
_WORD = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{4,}")


def _typos(word: str) -> list[str]:
    """Every single sound error that fits `word`, lowercase."""
    lower = word.lower()
    options = [lower.replace(a, b, 1) for a, b in _SOUND_SWAPS if a in lower]
    if lower.startswith("h"):
        options.append(lower[1:])
    if lower.translate(_ACCENTS) != lower:
        options.append(lower.translate(_ACCENTS))
    return options


def asr_typos(text: str, rng: Random) -> str:
    """Sound errors on some words of four letters or more, at least one when any fits.

    Each typo keeps the word's capital: what the ASR loses by sound, not by case.
    """
    words = [m for m in _WORD.finditer(text) if _typos(m.group())]
    if not words:
        return text
    picked = [m for m in words if rng.random() < _TYPO_RATE] or [rng.choice(words)]
    out, pos = [], 0
    for match in picked:
        word = match.group()
        typo = rng.choice(_typos(word))
        out += [
            text[pos : match.start()],
            typo[:1].upper() + typo[1:] if word[0].isupper() else typo,
        ]
        pos = match.end()
    out.append(text[pos:])
    return "".join(out)


_AV = re.compile(r"(?<!\w)(?:Av\.|Avda\.?|Avenida)\s+", re.IGNORECASE)


def without_av(text: str) -> str:
    return _AV.sub("", text)


# --- Ubicación noise -----------------------------------------------------------------------------

# Streets to say by mistake before the right one, when the ubicación has no altura to change.
_DECOYS = ("Av. Rivadavia 4500", "Av. Santa Fe 3200", "Av. Cabildo 2100", "Av. Belgrano 1800")
# What introduces a ubicación and is left hanging when it is cut: "en la", "cerca de", "esquina de".
_LEAD_IN = re.compile(
    r"(?:\s*,)?\s*(?:\b(?:en|de|del|al|el|la|los|las|sobre|por|desde|hasta|frente a|cerca de"
    r"|esquina|a la altura de)\b\s*)+$",
    re.IGNORECASE,
)


def _location(text: str) -> tuple[int, int, int | None] | None:
    """Where the Lector por reglas reads a ubicación in `text` (its first evidence) and the
    altura it reads there, if any."""
    reading = read_turn_location(Turn(index=0, at_ms=0, speaker=Speaker.LLAMANTE, text=text))
    if reading is None or not reading.evidence:
        return None
    altura = reading.number.value if reading.number else None
    return reading.evidence[0].start, reading.evidence[0].end, altura


def self_correction(text: str, rng: Random) -> str:
    """Say a wrong ubicación first, then correct it: "1450, no, perdón, Av. Corrientes 1540".

    With an altura, the wrong one is the same street at another altura (the usual slip);
    without one, it is another street.
    """
    found = _location(text)
    if found is None:
        return text
    start, end, altura = found
    said = text[start:end]
    # The altura as written: the last time it appears, so "25 de Mayo" is not taken for one.
    at = said.rfind(str(altura)) if altura is not None else -1
    if altura is not None and at >= 0:
        wrong = altura + rng.choice((-1, 1)) * 100 * rng.randint(1, 9)
        wrong = wrong if wrong > 0 else altura + 100 * rng.randint(1, 9)
        wrong_said = f"{said[:at]}{wrong}{said[at + len(str(altura)) :]}"
    else:
        wrong_said = rng.choice([d for d in _DECOYS if d.split()[1] not in said])
    return f"{text[:start]}{wrong_said}, no, perdón, {said}{text[end:]}"


_MAX_CUTS = 4


def without_location(text: str) -> str:
    """The turno with every ubicación the rules read cut out, with the words that led to it."""
    for _ in range(_MAX_CUTS):
        found = _location(text)
        if found is None:
            break
        start, end, _ = found
        head = _LEAD_IN.sub("", text[:start])
        text = f"{head}{text[end:]}"
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"([,.!?¿¡])(?:\s*,)+", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).lstrip(" ,.").rstrip(" ,")


# --- Variantes -----------------------------------------------------------------------------------

_TEXT_NOISE: dict[NoiseKind, Callable[[str, Random], str]] = {
    NoiseKind.MULETILLAS: add_fillers,
    NoiseKind.NUMEROS_EN_PALABRAS: lambda text, _: numbers_in_words(text),
    NoiseKind.TYPOS_ASR: asr_typos,
    NoiseKind.AUTOCORRECCION: self_correction,
    NoiseKind.SIN_AV: lambda text, _: without_av(text),
    NoiseKind.MINUSCULAS: lambda text, _: text.lower(),
    NoiseKind.SIN_DIRECCION: lambda text, _: without_location(text),
}


def rng_for(case_id: str, kind: NoiseKind, seed: int = SEED) -> Random:
    """One generator per case and kind: adding a case or a kind does not shift the others."""
    return Random(f"{seed}:{case_id}:{kind.value}")


def make_variant(
    case_id: str, turns: Sequence[ParsedTurn], kind: NoiseKind, seed: int = SEED
) -> Variant:
    rng = rng_for(case_id, kind, seed)
    noise = _TEXT_NOISE[kind]
    noisy = [
        t.model_copy(update={"text": noise(t.text, rng)}) if t.speaker is Speaker.LLAMANTE else t
        for t in turns
    ]
    applied = any(a.text != b.text for a, b in zip(noisy, turns, strict=True))
    return Variant(case_id=case_id, kind=kind, applied=applied, turns=noisy)


def make_variants(cases: Sequence[CatalogCase], kind: NoiseKind, seed: int = SEED) -> list[Variant]:
    return [make_variant(c.id, parse_transcript(c.transcript), kind, seed) for c in cases]


def variants_path(kind: NoiseKind, directory: Path = NOISY_DIR) -> Path:
    return directory / f"{kind.value}.json"


def dump_variants(variants: Sequence[Variant]) -> str:
    """The file content for one kind: stable, readable and diffable."""
    payload = [v.model_dump(mode="json") for v in variants]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def load_variants(kind: NoiseKind, directory: Path = NOISY_DIR) -> list[Variant]:
    path = variants_path(kind, directory)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Variant.model_validate(item) for item in raw]


def write_all(cases: Sequence[CatalogCase], directory: Path = NOISY_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for kind in NoiseKind:
        path = variants_path(kind, directory)
        path.write_text(dump_variants(make_variants(cases, kind)), encoding="utf-8")
        paths.append(path)
    return paths


def main() -> None:
    cases = parse_dataset(REPO_ROOT / "data" / "dataset_challenge_soflex.csv")
    for path in write_all(cases):
        variants = load_variants(NoiseKind(path.stem), path.parent)
        applied = sum(v.applied for v in variants)
        print(f"{path.relative_to(REPO_ROOT)}: {applied}/{len(variants)} con ruido")


if __name__ == "__main__":
    main()
