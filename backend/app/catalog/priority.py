"""Tabla de prioridad (DESIGN §Paso 5): auditable rules over señales, never decided by the IA.

Rules are ordered: within a level, the more critical rule first. The first rule whose
conditions all hold sets the prioridad, and its señales are the porqué.

When no rule fires, the incidente gets the base prioridad of its tipo (EDA, implicancia 6),
except a `reclamo` subtipo with no risk señal at all, which is P4 (EDA, implicancia 7: P4 is
our assumption, the dataset has none).

Some P1 rules (motociclista herido, heridos o menores expuestos a humo, gas que entra a las
casas, cable caído con descarga) go beyond the DESIGN examples: they come from the triggers the
EDA found behind the dataset's P1 cases.
"""

from pydantic import BaseModel, ConfigDict

from app.catalog.models import Category, Priority
from app.catalog.signals import SignalAnswer, SignalId


class SignalCondition(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: SignalId
    value: SignalAnswer = SignalAnswer.SI


class PriorityRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    level: Priority
    label: str
    when: tuple[SignalCondition, ...]


def _rule(
    rule_id: str, level: Priority, label: str, *when: SignalId | SignalCondition
) -> PriorityRule:
    conditions = tuple(
        c if isinstance(c, SignalCondition) else SignalCondition(signal_id=c) for c in when
    )
    return PriorityRule(id=rule_id, level=level, label=label, when=conditions)


def _no(signal_id: SignalId) -> SignalCondition:
    return SignalCondition(signal_id=signal_id, value=SignalAnswer.NO)


S = SignalId
P1, P2 = Priority.P1, Priority.P2

PRIORITY_RULES: tuple[PriorityRule, ...] = (
    # P1 · hay una vida en riesgo ahora
    _rule("no_respira", P1, "No respira", _no(S.RESPIRA)),
    _rule("inconsciente", P1, "Inconsciente", _no(S.CONSCIENTE)),
    _rule("atrapada_humo", P1, "Persona atrapada con humo", S.PERSONA_ATRAPADA, S.HUMO),
    _rule("atrapada_fuego", P1, "Persona atrapada con fuego", S.PERSONA_ATRAPADA, S.FUEGO_ACTIVO),
    _rule("atrapado_vehiculo", P1, "Atrapado en un vehículo", S.ATRAPADO_VEHICULO),
    _rule("explosion", P1, "Explosión", S.EXPLOSION),
    _rule("arma_fuego", P1, "Arma de fuego", S.ARMA_FUEGO),
    _rule("sangrado_abundante", P1, "Sangrado abundante", S.SANGRADO_ABUNDANTE),
    _rule("heridos_humo", P1, "Heridos expuestos a humo", S.HERIDOS, S.HUMO),
    _rule("heridos_fuego", P1, "Heridos expuestos a fuego", S.HERIDOS, S.FUEGO_ACTIVO),
    _rule("menores_humo", P1, "Menores expuestos a humo", S.MENORES, S.HUMO),
    _rule("menores_fuego", P1, "Menores expuestos a fuego", S.MENORES, S.FUEGO_ACTIVO),
    _rule("gas_propagacion", P1, "Gas que se extiende", S.GAS, S.PROPAGACION),
    _rule("descarga_electrica", P1, "Cable con descarga", S.CABLES_CAIDOS, S.RIESGO_ELECTRICO),
    _rule("motociclista_herido", P1, "Motociclista herido", S.MOTOCICLISTA, S.HERIDOS),
    # P2 · urgente, puede empeorar
    _rule("persona_atrapada", P2, "Persona atrapada", S.PERSONA_ATRAPADA),
    _rule("dificultad_respirar", P2, "Le cuesta respirar", S.DIFICULTAD_RESPIRAR),
    _rule("golpe_cabeza", P2, "Golpe en la cabeza", S.GOLPE_CABEZA),
    _rule("fuego_activo", P2, "Fuego activo", S.FUEGO_ACTIVO),
    _rule("humo", P2, "Humo", S.HUMO),
    _rule("gas", P2, "Gas", S.GAS),
    _rule("cables_caidos", P2, "Cables caídos", S.CABLES_CAIDOS),
    _rule("riesgo_electrico", P2, "Riesgo eléctrico", S.RIESGO_ELECTRICO),
    _rule("derrame_combustible", P2, "Derrame de combustible", S.DERRAME_COMBUSTIBLE),
    _rule("estructura_cede", P2, "Estructura que cede", S.ESTRUCTURA_CEDE),
    _rule("agua_sube", P2, "El agua sube", S.AGUA_SUBE),
    _rule("arma_blanca", P2, "Arma blanca", S.ARMA_BLANCA),
    _rule("heridos", P2, "Heridos", S.HERIDOS),
    _rule("involucrados_en_lugar", P2, "Involucrados en el lugar", S.INVOLUCRADOS_EN_LUGAR),
    _rule("propagacion", P2, "Se propaga", S.PROPAGACION),
)

# P3 is never set by a señal: it is "sin riesgo inmediato", the floor of most tipos.
BASE_PRIORITY: dict[Category, Priority] = {
    Category.INCENDIO_RESCATE: Priority.P3,
    Category.EMERGENCIA_MEDICA: Priority.P2,
    Category.ACCIDENTE_VIAL: Priority.P3,
    Category.DEFENSA_CIVIL: Priority.P2,
    Category.SERVICIOS_PUBLICOS: Priority.P3,
    Category.CONVIVENCIA_SEGURIDAD: Priority.P3,
}
BASE_LABEL = "Sin señales de riesgo: prioridad base del tipo"
RECLAMO_LABEL = "Reclamo sin ninguna señal de riesgo"
