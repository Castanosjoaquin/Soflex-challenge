"""The curated catalog is consistent: every reference points to something that exists."""

from app.catalog.incidents import SUBTYPES, TYPES, Subtype, subtypes_of
from app.catalog.models import Category, Priority
from app.catalog.priority import BASE_PRIORITY, PRIORITY_RULES
from app.catalog.questions import KEY_QUESTIONS, checklist_for
from app.catalog.signals import INCOHERENT_PAIRS, SIGNALS, VICTIM_SIGNALS, SignalId


def test_every_signal_is_defined_once_with_a_question() -> None:
    assert set(SIGNALS) == set(SignalId)
    assert 20 <= len(SIGNALS) <= 30
    for signal_id, signal in SIGNALS.items():
        assert signal.id is signal_id
        assert signal.label
        assert signal.question_hint.startswith("¿")


def test_every_tipo_has_a_label_and_subtipos() -> None:
    assert set(TYPES) == set(Category)
    for category in Category:
        assert subtypes_of(category), category


def test_every_subtipo_belongs_to_one_tipo() -> None:
    assert set(SUBTYPES) == set(Subtype)
    for subtype_id, subtype in SUBTYPES.items():
        assert subtype.id is subtype_id
        assert subtype.category in TYPES
        assert subtype.label


def test_priority_rules_are_unique_ordered_and_only_set_p1_or_p2() -> None:
    ids = [r.id for r in PRIORITY_RULES]
    assert len(ids) == len(set(ids))
    levels = [r.level for r in PRIORITY_RULES]
    assert levels == sorted(levels)
    assert set(levels) <= {Priority.P1, Priority.P2}
    for rule in PRIORITY_RULES:
        assert rule.when, rule.id
        assert all(c.signal_id in SIGNALS for c in rule.when)


def test_base_priority_covers_every_tipo_without_p1_or_p4() -> None:
    assert set(BASE_PRIORITY) == set(Category)
    assert set(BASE_PRIORITY.values()) <= {Priority.P2, Priority.P3}


def test_p4_is_reachable_only_through_a_reclamo() -> None:
    assert any(s.reclamo for s in SUBTYPES.values())


def test_coherence_and_victim_signals_exist() -> None:
    for left, right in INCOHERENT_PAIRS:
        assert left[0] in SIGNALS and right[0] in SIGNALS
    assert set(SIGNALS) >= VICTIM_SIGNALS


def test_every_key_question_points_to_an_existing_signal_and_subtipo_of_its_tipo() -> None:
    for question_id, question in KEY_QUESTIONS.items():
        assert question.id == question_id
        assert question.signal_id in SIGNALS
        assert question.text.startswith("¿"), question_id
        for subtype in question.subtypes:
            assert SUBTYPES[subtype].category is question.type, question_id


def test_every_tipo_and_subtipo_has_a_checklist_with_a_critical_question() -> None:
    for category in Category:
        for subtype in (None, *(s.id for s in subtypes_of(category))):
            checklist = checklist_for(category, subtype)
            assert any(q.critical for q in checklist), (category, subtype)
            signals = [q.signal_id for q in checklist]
            assert len(signals) == len(set(signals)), (category, subtype)
            assert [q.order for q in checklist] == sorted(q.order for q in checklist)


def test_a_subtipo_question_replaces_the_one_of_its_tipo_for_the_same_signal() -> None:
    general = [q.id for q in checklist_for(Category.ACCIDENTE_VIAL, None)]
    moto = [q.id for q in checklist_for(Category.ACCIDENTE_VIAL, Subtype.CHOQUE_MOTO)]
    assert "vial_casco" not in general
    assert moto[:2] == ["vial_atrapados", "vial_casco"]
