"""Señales: the closed list of atomic data the relato can affirm or deny (SPEC §4).

Both lectores may only propose señales from this list. Each one is tied to a question the operador
can ask when it is still unknown.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SignalId(StrEnum):
    PERSONA_ATRAPADA = "persona_atrapada"
    RESPIRA = "respira"
    CONSCIENTE = "consciente"
    FUEGO_ACTIVO = "fuego_activo"
    HUMO = "humo"
    GAS = "gas"
    RIESGO_ELECTRICO = "riesgo_electrico"
    ARMA_FUEGO = "arma_fuego"
    ARMA_BLANCA = "arma_blanca"
    SANGRADO_ABUNDANTE = "sangrado_abundante"
    HERIDOS = "heridos"
    MENORES = "menores"
    EVACUADO = "evacuado"
    PROPAGACION = "propagacion"
    DERRAME_COMBUSTIBLE = "derrame_combustible"
    ATRAPADO_VEHICULO = "atrapado_vehiculo"
    MOTOCICLISTA = "motociclista"
    AGUA_SUBE = "agua_sube"
    ESTRUCTURA_CEDE = "estructura_cede"
    CABLES_CAIDOS = "cables_caidos"
    INVOLUCRADOS_EN_LUGAR = "involucrados_en_lugar"
    ANIMAL_MORDEDURA = "animal_mordedura"
    EXPLOSION = "explosion"
    DIFICULTAD_RESPIRAR = "dificultad_respirar"
    GOLPE_CABEZA = "golpe_cabeza"


class SignalAnswer(StrEnum):
    SI = "si"
    NO = "no"
    NO_SABE = "no_sabe"


class SignalDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: SignalId
    label: str
    question_hint: str


def _signal(signal_id: SignalId, label: str, question_hint: str) -> SignalDef:
    return SignalDef(id=signal_id, label=label, question_hint=question_hint)


SIGNALS: dict[SignalId, SignalDef] = {
    s.id: s
    for s in (
        _signal(
            SignalId.PERSONA_ATRAPADA, "Persona atrapada", "¿Quedó alguien adentro o atrapado?"
        ),
        _signal(SignalId.RESPIRA, "Respira", "¿Respira?"),
        _signal(SignalId.CONSCIENTE, "Consciente", "¿Está consciente? ¿Le responde?"),
        _signal(SignalId.FUEGO_ACTIVO, "Fuego activo", "¿Hay fuego o llamas ahora?"),
        _signal(SignalId.HUMO, "Humo", "¿Hay humo? ¿De qué color?"),
        _signal(SignalId.GAS, "Gas", "¿Hay olor a gas, garrafas o caños de gas?"),
        _signal(
            SignalId.RIESGO_ELECTRICO,
            "Riesgo eléctrico",
            "¿Hay chispas, tableros o cables con luz?",
        ),
        _signal(SignalId.ARMA_FUEGO, "Arma de fuego", "¿Hay armas de fuego o escuchó disparos?"),
        _signal(SignalId.ARMA_BLANCA, "Arma blanca", "¿Hay cuchillos u otras armas blancas?"),
        _signal(
            SignalId.SANGRADO_ABUNDANTE, "Sangrado abundante", "¿Sangra mucho? ¿Se puede frenar?"
        ),
        _signal(SignalId.HERIDOS, "Heridos", "¿Hay heridos? ¿Cuántos?"),
        _signal(SignalId.MENORES, "Menores", "¿Hay chicos involucrados?"),
        _signal(SignalId.EVACUADO, "Evacuado", "¿Salieron todos? ¿Están afuera?"),
        _signal(SignalId.PROPAGACION, "Propagación", "¿Se está extendiendo a linderos o pisos?"),
        _signal(
            SignalId.DERRAME_COMBUSTIBLE, "Derrame de combustible", "¿Hay combustible derramado?"
        ),
        _signal(
            SignalId.ATRAPADO_VEHICULO,
            "Atrapado en vehículo",
            "¿Alguien quedó atrapado en o debajo de un vehículo?",
        ),
        _signal(SignalId.MOTOCICLISTA, "Motociclista", "¿Hay una moto involucrada?"),
        _signal(SignalId.AGUA_SUBE, "El agua sube", "¿El agua sigue subiendo o entrando?"),
        _signal(SignalId.ESTRUCTURA_CEDE, "Estructura que cede", "¿Algo se está cayendo o cede?"),
        _signal(SignalId.CABLES_CAIDOS, "Cables caídos", "¿Hay cables cortados o en el piso?"),
        _signal(
            SignalId.INVOLUCRADOS_EN_LUGAR,
            "Involucrados en el lugar",
            "¿Los involucrados siguen ahí?",
        ),
        _signal(SignalId.ANIMAL_MORDEDURA, "Ataque de animal", "¿El animal mordió a alguien?"),
        _signal(SignalId.EXPLOSION, "Explosión", "¿Hubo una explosión?"),
        _signal(SignalId.DIFICULTAD_RESPIRAR, "Dificultad para respirar", "¿Le cuesta respirar?"),
        _signal(SignalId.GOLPE_CABEZA, "Golpe en la cabeza", "¿Se golpeó la cabeza?"),
    )
}

# Señales whose combination is incoherent (SPEC §5.4.2): if the relato affirms both, neither is
# trusted and both go to a_confirmar. Someone who is conscious is breathing; someone trapped
# inside has not been evacuated.
type SignalFact = tuple[SignalId, SignalAnswer]

INCOHERENT_PAIRS: tuple[tuple[SignalFact, SignalFact], ...] = (
    ((SignalId.RESPIRA, SignalAnswer.NO), (SignalId.CONSCIENTE, SignalAnswer.SI)),
    ((SignalId.PERSONA_ATRAPADA, SignalAnswer.SI), (SignalId.EVACUADO, SignalAnswer.SI)),
)

# Señales that mean there is a víctima: when any of them is "sí", the universal questions
# (¿consciente? ¿respira?) come first (DESIGN §Paso 5, as in MPDS).
VICTIM_SIGNALS: frozenset[SignalId] = frozenset(
    {
        SignalId.PERSONA_ATRAPADA,
        SignalId.ATRAPADO_VEHICULO,
        SignalId.HERIDOS,
        SignalId.SANGRADO_ABUNDANTE,
        SignalId.GOLPE_CABEZA,
        SignalId.DIFICULTAD_RESPIRAR,
    }
)
