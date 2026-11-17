"""Relato text helpers shared by the lectores and the verificación."""

import re

_FOLD = str.maketrans("ÁÉÍÓÚÜÑáéíóúüñ", "AEIOUUNaeiouun")


def fold(text: str) -> str:
    """Lowercase without accents. Same length as `text`, so every offset stays valid."""
    folded = text.translate(_FOLD)
    lowered = folded.lower()
    if len(lowered) == len(folded):
        return lowered
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in folded)


_SOUNDS = ((re.compile(r"v"), "b"), (re.compile(r"z"), "s"), (re.compile(r"c(?=[ei])"), "s"))


def by_sound(folded: str) -> str:
    """A folded text as it sounds in rioplatense Spanish, where an ASR mixes letters up.

    b/v, s/z and s/c before e or i (SPEC §5.5): "poso" and "pozo", "devajo" and "debajo" read
    alike. Only the swaps of one letter for one, so every offset stays valid.
    """
    for pattern, replacement in _SOUNDS:
        folded = pattern.sub(replacement, folded)
    return folded
