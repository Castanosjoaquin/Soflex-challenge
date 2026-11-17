"""Text helpers for the rules: match on a normalized, folded copy; keep offsets on the original."""

import re
from dataclasses import dataclass

from app.readers.models import Evidence
from app.transcript.models import Turn
from app.transcript.normalize import Normalized, normalize

_CLAUSE_END = re.compile(r"[.,;:!?¡¿]")
# Function words a cut phrase should not end on ("humo negro con olor a" → "humo negro con olor").
_DANGLING = re.compile(r"(?:\s+(?:a|al|con|de|del|el|la|las|los|que|y|en|por|un|una))+$", re.I)


def extend_to_clause(text: str, start: int, end: int, limit: int) -> int:
    """Grow a match up to the end of its clause, at most `limit` chars, cutting at a word."""
    stop = _CLAUSE_END.search(text, end)
    clause_end = stop.start() if stop else len(text)
    if clause_end - start <= limit:
        return clause_end
    cut = text.rfind(" ", end, start + limit)
    if cut <= end:
        return end
    dangling = _DANGLING.search(text, start, cut)
    return max(dangling.start() if dangling else cut, end)


def clause_start(text: str, pos: int) -> int:
    """Where the clause holding `pos` begins: after the last punctuation or "pero"."""
    head = text[:pos]
    starts = [m.end() for m in _CLAUSE_END.finditer(head)]
    starts += [m.end() for m in re.finditer(r"\bpero\b", head)]
    return max(starts, default=0)


@dataclass(frozen=True)
class NormalizedTurn:
    """A llamante turno as the rules read it: normalized text, evidence on the original one."""

    original: Turn
    normalized: Normalized

    @classmethod
    def of(cls, turn: Turn) -> "NormalizedTurn":
        return cls(turn, normalize(turn.text))

    @property
    def turn(self) -> Turn:
        """The turno with its normalized text, for the patterns to run on."""
        return self.original.model_copy(update={"text": self.normalized.text})

    def evidence(self, start: int, end: int) -> Evidence:
        """Evidence for a span of the normalized text, located on the original turno text."""
        first, last = self.normalized.to_original(start, end)
        return Evidence(
            turn_index=self.original.index,
            start=first,
            end=last,
            quote=self.original.text[first:last],
        )
