"""Preguntas clave: the protocol checklist per tipo, with a few per subtipo (SPEC §5.7).

The base is the canonical checklist the EDA (§5) built from the dataset's mandatorias. Each
question is tied to one señal: it counts as answered when that señal is known, so the relato can
pre-mark it and the operador's answer is stored as that señal.

`order` is criticality: lower goes first. A subtipo question tied to the same señal as a question
of its tipo replaces it in that subtipo's checklist (same fact, asked the way that subtipo needs).
`critical` questions are the ones etapa ③ waits for.

What the universal questions cover (¿consciente? ¿respira?) is not repeated here: it belongs to
etapa ②.
"""

from pydantic import BaseModel, ConfigDict

from app.catalog.incidents import Subtype
from app.catalog.models import Category
from app.catalog.signals import SignalId


class KeyQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: Category
    subtypes: tuple[Subtype, ...] = ()
    text: str
    signal_id: SignalId
    order: int
    critical: bool = False


def _q(
    question_id: str,
    category: Category,
    order: int,
    signal_id: SignalId,
    text: str,
    *,
    critical: bool = False,
    subtypes: tuple[Subtype, ...] = (),
) -> KeyQuestion:
    return KeyQuestion(
        id=question_id,
        type=category,
        subtypes=subtypes,
        text=text,
        signal_id=signal_id,
        order=order,
        critical=critical,
    )


S, T = SignalId, Subtype
_I, _M, _A = Category.INCENDIO_RESCATE, Category.EMERGENCIA_MEDICA, Category.ACCIDENTE_VIAL
_D, _S, _C = Category.DEFENSA_CIVIL, Category.SERVICIOS_PUBLICOS, Category.CONVIVENCIA_SEGURIDAD

# Incendio: who is inside goes first; with someone known inside, "¿salieron todos?" adds little,
# so it goes after gas and propagación (DESIGN §Paso 6 has the gas question next in caso 001).
_INCENDIO = (
    _q(
        "inc_atrapados",
        _I,
        10,
        S.PERSONA_ATRAPADA,
        "¿Hay personas atrapadas o adentro?",
        critical=True,
    ),
    _q(
        "inc_gas",
        _I,
        20,
        S.GAS,
        "¿Hay garrafas o una conexión de gas cerca del fuego?",
        critical=True,
    ),
    _q(
        "inc_propagacion",
        _I,
        30,
        S.PROPAGACION,
        "¿El fuego o el humo pasa a otros locales o a pisos de arriba?",
        critical=True,
    ),
    _q("inc_evacuado", _I, 40, S.EVACUADO, "¿Salieron todos del lugar?"),
    _q("inc_electrico", _I, 50, S.RIESGO_ELECTRICO, "¿Hay riesgo eléctrico (tablero, cables)?"),
    _q("inc_heridos", _I, 60, S.HERIDOS, "¿Hay heridos o quemados?"),
    # Subtipos
    _q(
        "inc_litio",
        _I,
        15,
        S.RIESGO_ELECTRICO,
        "¿Hay baterías de litio (monopatín, bici eléctrica) o tableros cerca del fuego?",
        critical=True,
        subtypes=(T.INCENDIO_ELECTRICO,),
    ),
    _q(
        "inc_combustible",
        _I,
        15,
        S.DERRAME_COMBUSTIBLE,
        "¿Pierde combustible el vehículo?",
        critical=True,
        subtypes=(T.INCENDIO_VEHICULO, T.DERRAME_PELIGROSO),
    ),
)

_VIAL = (
    _q(
        "vial_atrapados",
        _A,
        10,
        S.ATRAPADO_VEHICULO,
        "¿Alguien quedó atrapado en o debajo de un vehículo?",
        critical=True,
    ),
    _q("vial_heridos", _A, 20, S.HERIDOS, "¿Hay heridos? ¿Cuántos?", critical=True),
    _q(
        "vial_combustible",
        _A,
        30,
        S.DERRAME_COMBUSTIBLE,
        "¿Hay combustible derramado o humo?",
        critical=True,
    ),
    _q("vial_moto", _A, 40, S.MOTOCICLISTA, "¿Hay una moto involucrada?"),
    _q("vial_menores", _A, 50, S.MENORES, "¿Hay chicos involucrados?"),
    # Subtipos: the casco is a head injury question, and it carries the "no se lo saquen".
    _q(
        "vial_casco",
        _A,
        15,
        S.GOLPE_CABEZA,
        "¿Se golpeó la cabeza? ¿Tiene el casco puesto? (que NO se lo saquen)",
        critical=True,
        subtypes=(T.CHOQUE_MOTO,),
    ),
)

_MEDICA = (
    _q("med_respirar", _M, 10, S.DIFICULTAD_RESPIRAR, "¿Le cuesta respirar?", critical=True),
    _q(
        "med_sangrado",
        _M,
        20,
        S.SANGRADO_ABUNDANTE,
        "¿Sangra mucho? ¿Se puede frenar?",
        critical=True,
    ),
    _q("med_golpe", _M, 30, S.GOLPE_CABEZA, "¿Se cayó o se golpeó la cabeza?"),
    _q("med_menor", _M, 40, S.MENORES, "¿Es un chico o una chica?"),
    # Subtipos
    _q(
        "med_garganta",
        _M,
        10,
        S.DIFICULTAD_RESPIRAR,
        "¿Se le cierra la garganta o le cuesta respirar?",
        critical=True,
        subtypes=(T.ALERGIA_GRAVE,),
    ),
    _q(
        "med_caida",
        _M,
        15,
        S.GOLPE_CABEZA,
        "¿Se golpeó la cabeza al caer?",
        critical=True,
        subtypes=(T.TRAUMATISMO, T.CONVULSION, T.PERDIDA_CONCIENCIA),
    ),
)

_DEFENSA = (
    _q(
        "dc_atrapados",
        _D,
        10,
        S.PERSONA_ATRAPADA,
        "¿Hay personas atrapadas o aisladas?",
        critical=True,
    ),
    _q("dc_cables", _D, 20, S.CABLES_CAIDOS, "¿Hay cables caídos o con luz?", critical=True),
    _q("dc_gas", _D, 30, S.GAS, "¿Hay olor a gas?", critical=True),
    _q("dc_cede", _D, 40, S.ESTRUCTURA_CEDE, "¿Algo sigue cediendo o cayéndose?"),
    _q("dc_heridos", _D, 50, S.HERIDOS, "¿Hay heridos?"),
    _q("dc_evacuado", _D, 60, S.EVACUADO, "¿Se evacuó o se aisló la zona?"),
    # Subtipos
    _q(
        "dc_agua",
        _D,
        15,
        S.AGUA_SUBE,
        "¿El agua sigue subiendo o entrando?",
        critical=True,
        subtypes=(T.INUNDACION,),
    ),
    _q(
        "dc_fuga",
        _D,
        5,
        S.GAS,
        "¿El olor a gas es fuerte o entra a las casas?",
        critical=True,
        subtypes=(T.FUGA_GAS,),
    ),
)

_SERVICIOS = (
    _q(
        "sp_heridos",
        _S,
        10,
        S.HERIDOS,
        "¿Hay heridos o personas o vehículos afectados?",
        critical=True,
    ),
    _q(
        "sp_electrico",
        _S,
        20,
        S.RIESGO_ELECTRICO,
        "¿Hay riesgo eléctrico (cables, agua sobre tableros)?",
        critical=True,
    ),
    _q("sp_empeora", _S, 30, S.ESTRUCTURA_CEDE, "¿Se agranda o sigue empeorando?"),
    # Subtipos
    _q(
        "sp_cables",
        _S,
        15,
        S.CABLES_CAIDOS,
        "¿Hay cables cortados o en el piso?",
        critical=True,
        subtypes=(T.CABLES_ELECTRICOS,),
    ),
    _q(
        "sp_agua",
        _S,
        25,
        S.AGUA_SUBE,
        "¿Sigue saliendo agua? ¿Llega a casas o comercios?",
        subtypes=(T.ROTURA_CANO_AGUA,),
    ),
)

_CONVIVENCIA = (
    _q(
        "cs_arma_fuego",
        _C,
        10,
        S.ARMA_FUEGO,
        "¿Hay armas de fuego o escuchó disparos?",
        critical=True,
    ),
    _q(
        "cs_arma_blanca",
        _C,
        20,
        S.ARMA_BLANCA,
        "¿Hay cuchillos u otras armas blancas?",
        critical=True,
    ),
    _q("cs_heridos", _C, 30, S.HERIDOS, "¿Hay heridos?", critical=True),
    _q("cs_en_lugar", _C, 40, S.INVOLUCRADOS_EN_LUGAR, "¿Los involucrados siguen ahí?"),
    # Subtipos
    _q(
        "cs_mordedura",
        _C,
        5,
        S.ANIMAL_MORDEDURA,
        "¿El animal mordió a alguien?",
        critical=True,
        subtypes=(T.ANIMAL_SUELTO,),
    ),
)

KEY_QUESTIONS: dict[str, KeyQuestion] = {
    q.id: q for q in (*_INCENDIO, *_VIAL, *_MEDICA, *_DEFENSA, *_SERVICIOS, *_CONVIVENCIA)
}


def checklist_for(category: Category, subtype: Subtype | None) -> list[KeyQuestion]:
    """The checklist of a tipo and subtipo, by criticality, with one question per señal."""
    general = [q for q in KEY_QUESTIONS.values() if q.type is category and not q.subtypes]
    specific = [q for q in KEY_QUESTIONS.values() if subtype is not None and subtype in q.subtypes]
    replaced = {q.signal_id for q in specific}
    chosen = [q for q in general if q.signal_id not in replaced] + specific
    return sorted(chosen, key=lambda q: q.order)
