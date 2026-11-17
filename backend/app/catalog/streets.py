"""Official street list of CABA and the matcher that takes a said street to its official name.

The list is ``data/streets.json`` (BA Data "Calles", CC-BY; see ``scripts/build_streets.py``). It
ships with the app: matching never needs internet (SPEC §5.5).
"""

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from app.config import REPO_ROOT

STREETS_PATH = REPO_ROOT / "data" / "streets.json"


class MatchKind(StrEnum):
    EXACTO = "exacto"  # the official name
    ALIAS = "alias"  # a previous name or the surname alone ("Serrano", "Scalabrini Ortiz")
    FUZZY = "fuzzy"  # sounds like or looks like one ("Biyinghurst"): always to be confirmed


@dataclass(frozen=True)
class Street:
    name: str
    kind: str
    short: str | None = None
    previous: tuple[str, ...] = ()
    alturas: tuple[int, int] | None = None
    length_m: int = 0

    def has_altura(self, altura: int) -> bool:
        return self.alturas is not None and self.alturas[0] <= altura <= self.alturas[1]


@dataclass(frozen=True)
class StreetMatch:
    kind: MatchKind
    candidates: tuple[Street, ...]

    @property
    def official(self) -> str:
        return self.candidates[0].name

    @property
    def avenida_o_calle(self) -> bool:
        """The name is both an avenida and a calle, and nothing said tells which one."""
        avenidas = [s.kind == "avenida" for s in self.candidates]
        return any(avenidas) and not all(avenidas)


def fold(text: str) -> str:
    """Lowercase, no accents, no punctuation, single spaces: "Av. Entre Ríos" → "av entre rios"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


_AVENUE_WORDS = frozenset({"av", "avda", "avenida"})
# Titles as the official list abbreviates them, and as people say them.
_TITLES = {
    "alte": "almirante",
    "brig": "brigadier",
    "cap": "capitan",
    "cmte": "comandante",
    "cnel": "coronel",
    "dr": "doctor",
    "gral": "general",
    "ing": "ingeniero",
    "int": "intendente",
    "mcal": "mariscal",
    "pres": "presidente",
    "prof": "profesor",
    "pte": "presidente",
    "sgto": "sargento",
    "tte": "teniente",
}


_KIND_PREFIX = re.compile(r"^(?:av\.?|avda\.?|avenida|calle)\s+", re.IGNORECASE)


def bare_name(said: str) -> str:
    """The name without "Av."/"calle", as said in a question: "Av. Rivadavia" → "Rivadavia"."""
    return _KIND_PREFIX.sub("", said)


def _said_kind(said: str) -> str | None:
    """ "avenida" or "calle" when the llamante said so ("Av. Scalabrini Ortiz")."""
    words = fold(said).split()
    if not words:
        return None
    if words[0] in _AVENUE_WORDS:
        return "avenida"
    return "calle" if words[0] == "calle" else None


def _key(name: str) -> str:
    """The comparable part of a name, without "Av."/"calle" and with titles spelled out.

    "Avda. Gral. Paz" → "general paz".
    """
    words = fold(name).split()
    if words and (words[0] in _AVENUE_WORDS or words[0] == "calle"):
        words = words[1:]
    return " ".join(_TITLES.get(w, w) for w in words)


_SOUNDS = (
    (re.compile(r"v"), "b"),
    (re.compile(r"ll"), "y"),
    (re.compile(r"y\b"), "i"),
    (re.compile(r"z"), "s"),
    (re.compile(r"c(?=[ei])"), "s"),
    (re.compile(r"g(?=[ei])"), "j"),
    (re.compile(r"qu(?=[ei])|c|q"), "k"),
    (re.compile(r"(?<!k)h"), ""),  # h muda; "ch" was "kh" by now and keeps it
    (re.compile(r"\bes(?=[^aeiou\s])"), "s"),  # "Escalabrini" for "Scalabrini"
    (re.compile(r"(\w)\1+"), r"\1"),  # "Corientes" for "Corrientes"
)


def _sound(key: str) -> str:
    """How a key sounds in rioplatense Spanish: "billinghurst" and "biyinghurst" sound alike."""
    for pattern, replacement in _SOUNDS:
        key = pattern.sub(replacement, key)
    return key


def _short_forms(short: str | None) -> list[str]:
    """The surname and its first words: "SCALABRINI ORTIZ" → "SCALABRINI ORTIZ", "SCALABRINI"."""
    if short is None:
        return []
    words = short.split()
    prefixes = [" ".join(words[:n]) for n in range(1, len(words))]
    return [short, *(p for p in prefixes if len(p) >= _MIN_PREFIX)]


_MIN_PREFIX = 4


class StreetList:
    def __init__(self, streets: list[Street]) -> None:
        self._exact: dict[str, list[Street]] = defaultdict(list)
        self._alias: dict[str, list[Street]] = defaultdict(list)
        for street in streets:
            self._exact[_key(street.name)].append(street)
            for alias in {*street.previous, *_short_forms(street.short)}:
                self._alias[_key(alias)].append(street)
        self._by_sound: dict[str, set[Street]] = defaultdict(set)
        for index in (self._exact, self._alias):
            for key, found in index.items():
                self._by_sound[_sound(key)].update(found)
        self._sounds = list(self._by_sound)

    @classmethod
    def load(cls, path: Path) -> "StreetList":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            [
                Street(
                    name=s["name"],
                    kind=s["kind"],
                    short=s["short"],
                    previous=tuple(s["previous"]),
                    alturas=tuple(s["alturas"]) if s["alturas"] else None,
                    length_m=s["length_m"],
                )
                for s in data["streets"]
            ]
        )

    def match(self, said: str, altura: int | None = None) -> StreetMatch | None:
        key = _key(said)
        tiers = [
            (kind, found)
            for kind, index in ((MatchKind.EXACTO, self._exact), (MatchKind.ALIAS, self._alias))
            if (found := index.get(key))
        ]
        if not tiers and (found := self._sounds_like(key)):
            tiers = [(MatchKind.FUZZY, found)]
        if altura is None and tiers and tiers[0][0] is MatchKind.EXACTO:
            exact = tiers[0][1]
            tiers[0] = (MatchKind.EXACTO, exact + self._renamed_stretches(key, exact))
        if altura is not None:
            # A street renamed in part ("Serrano" → "Jorge Luis Borges" from 1601): the stretch
            # that has that altura wins, whatever tier it comes from.
            tiers = _narrowed(tiers, lambda s: s.has_altura(altura))
        if said_kind := _said_kind(said):
            tiers = _narrowed(tiers, lambda s: (s.kind == "avenida") == (said_kind == "avenida"))
        for kind, found in tiers:
            if found:
                ranked = sorted(set(found), key=lambda s: -s.length_m)
                return StreetMatch(kind=kind, candidates=tuple(ranked))
        return None

    def _renamed_stretches(self, key: str, streets: list[Street]) -> list[Street]:
        """Stretches that once had this name and continue its numbering.

        "Serrano" is still SERRANO up to 1600; from 1601 it was renamed JORGE LUIS BORGES. Without
        an altura both are possible. An old name reused elsewhere (RAMOS MEJIA was once partly
        "San Juan", within the alturas of AV. SAN JUAN) is not a continuation and is left out.
        """
        return [
            renamed
            for renamed in self._alias.get(key, [])
            if renamed not in streets
            and key in {_key(p) for p in renamed.previous}
            and all(_continues(street, renamed) for street in streets)
        ]

    def _sounds_like(self, key: str) -> list[Street]:
        """The streets whose name sounds most like the key, if any is close enough."""
        if len(key) < _MIN_FUZZY:
            return []
        hits = process.extract(
            _sound(key), self._sounds, scorer=fuzz.ratio, score_cutoff=_FUZZY_CUTOFF, limit=None
        )
        best = max((score for _, score, _ in hits), default=None)
        return [s for sound, score, _ in hits if score == best for s in self._by_sound[sound]]


def _continues(street: Street, renamed: Street) -> bool:
    """Both are numbered and their alturas do not overlap: one picks up where the other ends."""
    if street.alturas is None or renamed.alturas is None:
        return False
    return renamed.alturas[0] > street.alturas[1] or renamed.alturas[1] < street.alturas[0]


_Tiers = list[tuple[MatchKind, list[Street]]]


def _narrowed(tiers: _Tiers, keep: Callable[[Street], bool]) -> _Tiers:
    """Keep only the streets that pass, unless none does: then the clue is ignored."""
    narrowed = [(kind, [s for s in found if keep(s)]) for kind, found in tiers]
    return narrowed if any(found for _, found in narrowed) else tiers


_FUZZY_CUTOFF = 85
_MIN_FUZZY = 4  # shorter words sound like too many streets


@lru_cache
def official_streets() -> StreetList:
    return StreetList.load(STREETS_PATH)


def match_street(said: str, altura: int | None = None) -> StreetMatch | None:
    """The official street the llamante meant, or None when nothing in the list is close."""
    return official_streets().match(said, altura)
