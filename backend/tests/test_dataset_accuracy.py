"""How many of the 30 dataset llamadas get tipo and prioridad right in modo simulado.

It reports, it does not gate: there is no threshold. The keywords and rules were written looking
at these same 30 cases, so the number is optimistic (EDA §8); the honest one comes from the
eval runner on the noisy variants.
"""

import pytest

from app.api import _LINE_BY_SOURCE
from app.catalog.loader import parse_dataset
from app.engine.models import Line, Mode
from app.engine.state import add_turn, apply_reading, new_call
from app.readers.rules.reader import RulesReader
from app.transcript.models import Turn
from app.transcript.parser import parse_transcript
from tests.conftest import DATASET


def test_report_tipo_and_prioridad_hits(capsys: pytest.CaptureFixture[str]) -> None:
    reader = RulesReader()
    cases = parse_dataset(DATASET)
    misses: list[str] = []
    tipo_hits = priority_hits = both_hits = 0
    for case in cases:
        line = _LINE_BY_SOURCE.get(case.source, Line.L911)
        state = new_call(case.id, line, Mode.SIMULADO)
        for i, parsed in enumerate(parse_transcript(case.transcript)):
            turn = Turn(index=i, at_ms=0, speaker=parsed.speaker, text=parsed.text)
            state = add_turn(state, turn)
            state = apply_reading(state, reader.read(state.turns, line))
        tipo_ok = state.incident is not None and state.incident.category is case.category
        priority_ok = state.priority is not None and state.priority.level is case.priority
        tipo_hits += tipo_ok
        priority_hits += priority_ok
        both_hits += tipo_ok and priority_ok
        if not (tipo_ok and priority_ok):
            got_tipo = state.incident.category.value if state.incident else "—"
            got_priority = state.priority.level.value if state.priority else "—"
            misses.append(
                f"  {case.id}: tipo {got_tipo} (gold {case.category.value}), "
                f"prioridad {got_priority} (gold {case.priority.value})"
            )
    total = len(cases)
    with capsys.disabled():
        print(
            f"\n[modo simulado] tipo {tipo_hits}/{total} · prioridad {priority_hits}/{total} · "
            f"ambos {both_hits}/{total}"
        )
        print("\n".join(misses))
    assert total == 30
