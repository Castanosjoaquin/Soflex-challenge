"""The instrucciones catalog is consistent, and its contraindications hold (SPEC §5.8)."""

import itertools

import pytest

from app.catalog.incidents import SUBTYPES, Subtype
from app.catalog.instructions import (
    ACTION_ORDER,
    CONTRADICTORY,
    INSTRUCTIONS,
    INSTRUCTIONS_BY_ID,
    PROHIBITION_ORDER,
    InstructionCondition,
    instructions_for,
)
from app.catalog.models import Category, Priority
from app.catalog.priority import PRIORITY_RULES
from app.catalog.signals import SIGNALS, SignalAnswer, SignalId

RULES = {r.id: r for r in PRIORITY_RULES}
ALL_SI = dict.fromkeys(SignalId, SignalAnswer.SI)
ALL_RULES = frozenset(RULES)
PROHIBITION_STARTS = ("No ", "Nunca ", "Prohibido ")


def _ids(category: Category | None, subtype: Subtype | None, **kw: object) -> list[str]:
    signals = kw.get("signals", {})
    rules = kw.get("rules", frozenset())
    assert isinstance(signals, dict) and isinstance(rules, frozenset)
    return [i.id for i in instructions_for(category, subtype, signals, rules)]


def test_ids_are_unique_and_texts_short_imperative_phrases() -> None:
    assert len(INSTRUCTIONS_BY_ID) == len(INSTRUCTIONS)
    for instruction in INSTRUCTIONS:
        assert instruction.text.endswith("."), instruction.id
        assert len(instruction.text.split()) <= 20, instruction.id
        assert instruction.text[0].isupper(), instruction.id


def test_every_condition_points_to_existing_tipos_subtipos_senales_and_rules() -> None:
    for instruction in INSTRUCTIONS:
        when = instruction.applies_when
        for subtype in (*when.subtypes, *when.except_subtypes):
            assert subtype in SUBTYPES, instruction.id
            if when.types:
                assert SUBTYPES[subtype].category in when.types, instruction.id
        for condition in when.signals:
            assert condition.signal_id in SIGNALS, instruction.id
        for rule_id in when.priority_rules:
            assert rule_id in RULES, (instruction.id, rule_id)


def test_criticas_are_exactly_the_ones_tied_to_p1_rules_and_go_first() -> None:
    for instruction in INSTRUCTIONS:
        rules = instruction.applies_when.priority_rules
        assert instruction.critical is bool(rules), instruction.id
        assert all(RULES[r].level is Priority.P1 for r in rules), instruction.id
        assert (instruction.order < PROHIBITION_ORDER) is instruction.critical, instruction.id
        # A crítica cannot wait for the tipo: the señal may come first.
        if instruction.critical:
            assert not instruction.applies_when.types, instruction.id


def test_every_p1_rule_has_a_critica() -> None:
    covered = {r for i in INSTRUCTIONS for r in i.applies_when.priority_rules}
    p1 = {r.id for r in PRIORITY_RULES if r.level is Priority.P1}
    assert covered == p1


def test_prohibitions_go_before_the_rest() -> None:
    for instruction in INSTRUCTIONS:
        if instruction.critical:
            continue
        prohibition = instruction.text.startswith(PROHIBITION_STARTS)
        assert (instruction.order < ACTION_ORDER) is prohibition, instruction.id
    orders = [i.order for i in INSTRUCTIONS]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)


def _can_coexist(a: InstructionCondition, b: InstructionCondition) -> bool:
    """Whether some llamada makes both conditions hold at once."""
    if a.types and b.types and not set(a.types) & set(b.types):
        return False
    subtypes = set(Subtype)
    for when in (a, b):
        if when.subtypes:
            subtypes &= set(when.subtypes)
        subtypes -= set(when.except_subtypes)
    if (a.subtypes or b.subtypes) and not subtypes:
        return False
    values = {c.signal_id: c.value for c in a.signals}
    return all(values.get(c.signal_id, c.value) is c.value for c in b.signals)


def test_contradictory_instrucciones_never_apply_together() -> None:
    for left, right in CONTRADICTORY:
        a, b = INSTRUCTIONS_BY_ID[left].applies_when, INSTRUCTIONS_BY_ID[right].applies_when
        assert not _can_coexist(a, b), (left, right)


def test_only_one_reingreso_critica_fits_any_subtipo() -> None:
    reingreso = [i for i in INSTRUCTIONS if i.id.startswith("critica_no_reingresar")]
    for a, b in itertools.combinations(reingreso, 2):
        assert not _can_coexist(a.applies_when, b.applies_when), (a.id, b.id)


@pytest.mark.parametrize("subtype", list(Subtype))
def test_no_tire_agua_only_in_electrico_baterias_or_combustible(subtype: Subtype) -> None:
    ids = _ids(SUBTYPES[subtype].category, subtype, signals=ALL_SI, rules=ALL_RULES)
    water = {i for i in ids if i.startswith("no_agua")}
    allowed = {Subtype.INCENDIO_ELECTRICO, Subtype.DERRAME_PELIGROSO}
    assert bool(water) is (subtype in allowed)


def test_pastizal_never_says_no_tire_agua() -> None:
    texts = [
        i.text
        for i in instructions_for(
            Category.INCENDIO_RESCATE, Subtype.INCENDIO_PASTIZAL, ALL_SI, ALL_RULES
        )
    ]
    assert not any("tire agua" in t for t in texts)


def test_no_le_saque_el_casco_only_with_a_motociclista() -> None:
    without = {**ALL_SI, SignalId.MOTOCICLISTA: SignalAnswer.NO}
    assert "critica_no_sacar_casco" not in _ids(
        Category.ACCIDENTE_VIAL, Subtype.CHOQUE_MOTO, signals=without, rules=ALL_RULES
    )
    assert "critica_no_sacar_casco" in _ids(
        Category.ACCIDENTE_VIAL,
        Subtype.CHOQUE_MOTO,
        signals={SignalId.MOTOCICLISTA: SignalAnswer.SI, SignalId.HERIDOS: SignalAnswer.SI},
        rules=frozenset({"motociclista_herido"}),
    )


@pytest.mark.parametrize(
    ("subtype", "position"),
    [
        (Subtype.DIFICULTAD_RESPIRATORIA, "no_acostar"),
        (Subtype.ALERGIA_GRAVE, "no_acostar"),
        (Subtype.CONVULSION, "convulsion_lateral"),
        (Subtype.PERDIDA_CONCIENCIA, "piernas_elevadas"),
    ],
)
def test_the_patient_position_follows_the_cuadro(subtype: Subtype, position: str) -> None:
    positions = {"no_acostar", "convulsion_lateral", "piernas_elevadas", "no_esfuerzo"}
    ids = _ids(Category.EMERGENCIA_MEDICA, subtype, signals=ALL_SI, rules=ALL_RULES)
    assert set(ids) & positions == {position}


def test_an_unknown_subtipo_gets_no_subtipo_instruccion() -> None:
    assert _ids(Category.EMERGENCIA_MEDICA, None) == []
    assert _ids(Category.ACCIDENTE_VIAL, None) == ["senalizar"]


def test_a_critica_applies_before_the_tipo_is_known() -> None:
    ids = _ids(
        None,
        None,
        signals={SignalId.PERSONA_ATRAPADA: SignalAnswer.SI, SignalId.HUMO: SignalAnswer.SI},
        rules=frozenset({"atrapada_humo"}),
    )
    assert ids == ["critica_no_reingresar"]
