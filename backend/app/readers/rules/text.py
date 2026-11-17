"""Text helpers for the rules: match on a folded copy, keep offsets on the original."""

import re

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
