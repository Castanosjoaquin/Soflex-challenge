"""Relato text helpers shared by the lectores and the verificación."""

_FOLD = str.maketrans("ÁÉÍÓÚÜÑáéíóúüñ", "AEIOUUNaeiouun")


def fold(text: str) -> str:
    """Lowercase without accents. Same length as `text`, so every offset stays valid."""
    folded = text.translate(_FOLD)
    lowered = folded.lower()
    if len(lowered) == len(folded):
        return lowered
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in folded)
