"""The metrics of the evaluación, the gold files and how the runner counts the Lector con IA."""

import asyncio

from app.catalog.models import Category, Priority
from app.catalog.signals import SignalId
from app.config import LLMProviderName
from app.engine.models import Line
from app.eval.corpus import EvalCall, load_mandatorias
from app.eval.metrics import Confusion, Mandatoria, Rate, gold_altura, gold_street, rate
from app.eval.metrics import premark_confusion as confusion
from app.eval.report import RunResult, render
from app.eval.runner import Outcome, run_call
from app.readers.rules.reader import RulesReader
from app.transcript.models import ParsedTurn, Speaker
from tests.ia_fakes import FakeEndpoint, ia_reader

S = SignalId


def _m(answered: bool, *signals: SignalId) -> Mandatoria:
    return Mandatoria(case_id="001", text="¿…?", answered=answered, signal_ids=signals)


def test_rate() -> None:
    assert rate([True, False, True]) == Rate(2, 3)
    assert Rate(1, 2) + Rate(1, 2) == Rate(2, 4)
    assert Rate(0, 0).value is None


def test_gold_street_is_the_official_name() -> None:
    assert gold_street("Av. Corrientes") == "AV. CORRIENTES"
    assert gold_street("Av. Montes de Oca") == "AV. MANUEL MONTES DE OCA"
    assert gold_street("Carlos Pellegrini (Andén Subte Línea B)") == "CARLOS PELLEGRINI"


def test_gold_altura_only_when_the_relato_says_a_number() -> None:
    assert gold_altura("1540") == 1540
    assert gold_altura("4500 (esquina)") is None
    assert gold_altura("Km 7 (altura Parque Norte)") is None
    assert gold_altura("S/N (Rotonda Puente Alsina)") is None


def test_premarks_against_the_annotation() -> None:
    mandatorias = [
        _m(True, S.PERSONA_ATRAPADA),  # answered and marked: tp
        _m(False, S.GAS),  # not answered, marked: fp
        _m(True, S.PROPAGACION),  # answered, not marked: fn
        _m(False, S.HUMO),  # neither: tn
        _m(True),  # no señal answers it: out
        _m(True, S.ARMA_BLANCA, S.ARMA_FUEGO),  # either señal marks it: tp
    ]
    known = {S.PERSONA_ATRAPADA, S.GAS, S.ARMA_FUEGO}
    result = confusion(mandatorias, known)
    assert result == Confusion(tp=2, fp=1, fn=1, tn=1)
    assert result.precision == Rate(2, 3)
    assert result.recall == Rate(2, 3)


def test_the_gold_files_cover_the_90_mandatorias() -> None:
    by_case = load_mandatorias()
    assert len(by_case) == 30
    assert all(len(items) == 3 for items in by_case.values())
    assert by_case["001"][0].signal_ids == (S.PERSONA_ATRAPADA,)
    assert by_case["001"][0].answered


CALL = EvalCall(
    case_id="SFX-REC-2026-001",
    variant="original",
    applied=True,
    line=Line.L911,
    turns=[
        ParsedTurn(speaker=Speaker.OPERADOR, text="911 emergencias."),
        ParsedTurn(
            speaker=Speaker.LLAMANTE,
            text="En Av. Corrientes 1540 se prendió fuego la cocina y adentro quedó el cocinero!",
        ),
    ],
    street="AV. CORRIENTES",
    altura=1540,
    category=Category.INCENDIO_RESCATE,
    priority=Priority.P1,
    mandatorias=(),
)


def _run(replies: list[object]) -> Outcome:
    return asyncio.run(run_call(CALL, RulesReader(), ia_reader(FakeEndpoint(replies))))


def test_runner_counts_broken_answers_and_fallbacks() -> None:
    outcome = _run(["no es json", "tampoco"])
    assert (outcome.lecturas, outcome.broken, outcome.fallbacks) == (1, 1, 1)
    # The rules still read the llamada.
    assert outcome.street_ok and outcome.altura_ok and outcome.category_ok


def test_runner_counts_datos_dropped_for_lack_of_evidence() -> None:
    answer = {
        "location": None,
        "incident": {"category": "INCENDIO_RESCATE", "quote": "se prendió fuego", "turn": 1},
        "signals": [
            {"id": "persona_atrapada", "value": "si", "quote": "quedó el cocinero", "turn": 1},
            {"id": "gas", "value": "si", "quote": "hay una garrafa", "turn": 1},  # not said
            {"id": "inventada", "value": "si", "quote": "se prendió fuego", "turn": 1},
        ],
    }
    outcome = _run([answer])
    assert (outcome.broken, outcome.fallbacks) == (0, 0)
    assert (outcome.proposed, outcome.discarded) == (4, 2)


def test_report_marks_a_missing_run_as_pending() -> None:
    result = RunResult(provider=LLMProviderName.MOCK, outcomes=[_run(["roto", "roto"])])
    markdown = render({LLMProviderName.MOCK: result, LLMProviderName.OPENAI_COMPAT: None})
    assert "no se puede afirmar nada estadísticamente" in markdown
    assert "| Calle (nombre oficial) | 1/1 · 100 % | — | — | pendiente | pendiente | — |" in (
        markdown
    )
    assert "--provider openai_compat" in markdown
