"""Split a raw transcript into turnos by its `Operador:` / `Llamante:` prefixes (SPEC §5.1)."""

import re

from app.transcript.models import ParsedTurn, Speaker

_PREFIX = re.compile(r"\b(Operador|Llamante)\s*:", re.IGNORECASE)


def parse_transcript(raw: str) -> list[ParsedTurn]:
    """Return the turnos in order. Text without any prefix is a single turno of the llamante.

    Text before the first prefix is attributed to the llamante; empty turnos are dropped.
    """
    matches = list(_PREFIX.finditer(raw))
    if not matches:
        text = raw.strip()
        return [ParsedTurn(speaker=Speaker.LLAMANTE, text=text)] if text else []

    turns: list[ParsedTurn] = []
    preamble = raw[: matches[0].start()].strip()
    if preamble:
        turns.append(ParsedTurn(speaker=Speaker.LLAMANTE, text=preamble))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        text = raw[match.end() : end].strip()
        if text:
            turns.append(ParsedTurn(speaker=Speaker(match.group(1).lower()), text=text))
    return turns
