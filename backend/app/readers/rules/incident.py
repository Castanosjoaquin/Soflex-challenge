"""Rules-based tipo and subtipo: weighted keywords plus the línea as a prior (EDA, implicancia 5).

Every keyword points to a tipo, and most also to a subtipo. A tipo scores the weights of its
keywords found in the llamante's turnos; the línea adds a prior (107 → médica, 103 → defensa
civil, 147 → servicios) that only breaks ties between tipos the relato already mentions: with no
keyword there is no tipo. The subtipo is the best scored within the chosen tipo.

Negation does not matter here: "no hay fuego" still talks about a fire. Keywords run on the
normalized turno (SPEC §5.2); their evidence is located on the original text.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from app.catalog.incidents import SUBTYPES, Subtype
from app.catalog.models import Category
from app.engine.models import Line
from app.readers.models import Evidence, IncidentReading
from app.readers.rules.text import NormalizedTurn
from app.transcript.models import Speaker, Turn
from app.transcript.text import fold

C, T = Category, Subtype

# A lead smaller than this between the first two tipos means the lector is not sure.
CLEAR_MARGIN = 2

LINE_PRIOR: dict[Line, tuple[Category, int]] = {
    Line.L107: (C.EMERGENCIA_MEDICA, 3),
    Line.L103: (C.DEFENSA_CIVIL, 1),
    Line.L147: (C.SERVICIOS_PUBLICOS, 1),
}


@dataclass(frozen=True)
class _Keyword:
    category: Category
    subtype: Subtype | None
    weight: int
    regex: re.Pattern[str]


def _k(target: Category | Subtype, weight: int, pattern: str) -> _Keyword:
    if isinstance(target, Subtype):
        category, subtype = SUBTYPES[target].category, target
    else:
        category, subtype = target, None
    return _Keyword(category, subtype, weight, re.compile(rf"\b(?:{pattern})\b"))


_KEYWORDS: tuple[_Keyword, ...] = (
    # Incendio y rescate
    _k(C.INCENDIO_RESCATE, 3, r"fuego|llamas|llamarada|incendio|se prendio"),
    _k(C.INCENDIO_RESCATE, 2, r"humo|bomberos|quema|explot\w+|explosion"),
    _k(T.INCENDIO_VIVIENDA, 2, r"casa|departamento|depto|vivienda|monoambiente"),
    _k(
        T.INCENDIO_COMERCIO,
        2,
        r"pizzeria|restaurante|local|comercio|negocio|cocina|campana"
        r"|taller|fabrica|deposito|galpon",
    ),
    _k(
        T.INCENDIO_VEHICULO,
        3,
        r"(auto|camioneta|colectivo|vehiculo|motor) (se prendio|en llamas"
        r"|incendiad\w*)",
    ),
    _k(
        T.INCENDIO_ELECTRICO,
        3,
        r"tablero|cortocircuito|subestacion|transformador|baterias?(?! de semaforos)|litio",
    ),
    _k(T.INCENDIO_PASTIZAL, 2, r"pastos?|pastizal\w*|yuyos|malezas?"),
    _k(T.INCENDIO_PASTIZAL, 1, r"parque"),
    _k(T.INCENDIO_RESIDUOS, 2, r"contenedor|basura|residuos|volquete"),
    _k(T.DERRAME_PELIGROSO, 3, r"cisterna|gasoil|nafta|combustible|derrame|quimic\w+"),
    _k(T.RESCATE, 4, r"ascensor"),
    _k(T.RESCATE, 2, r"trabad[oa]|se trabo|encerrad\w+"),
    # Emergencia médica
    _k(C.EMERGENCIA_MEDICA, 3, r"ambulancia|medico|paramedicos"),
    _k(C.EMERGENCIA_MEDICA, 2, r"consciente|conciencia|no responde|dolor"),
    _k(
        T.DIFICULTAD_RESPIRATORIA,
        3,
        r"asma\w*|broncoespasmo|salbutamol|inhalador|no le entra el aire"
        r"|tiraje|labios morados|se ahoga\w*",
    ),
    _k(T.ALERGIA_GRAVE, 3, r"alergic[oa]|alergia|garganta|hinchad[oa]|ronchas|picadura"),
    _k(T.CONVULSION, 3, r"convuls\w+|sacudidas|espuma en la boca|epilep\w+"),
    _k(T.PERDIDA_CONCIENCIA, 3, r"desmay\w+|inconsciente|se desvanecio|perdio el conocimiento"),
    _k(T.TRAUMATISMO, 3, r"fractura\w*|tropezo|se cayo|caida|se golpeo|hueso|cadera"),
    _k(T.HEMORRAGIA, 3, r"sangr\w+|hemorragia"),
    _k(T.CARDIACO, 3, r"infarto|paro cardiaco|dolor (en el|de) pecho"),
    # Accidente vial
    _k(C.ACCIDENTE_VIAL, 1, r"autos?|camion|taxi|colectivo|carril|conductor|capot|guardarrail"),
    _k(C.ACCIDENTE_VIAL, 2, r"autopista|ruta"),
    _k(T.CHOQUE_VEHICULOS, 3, r"choque|choco|chocaron|colision\w*|en cadena"),
    _k(T.CHOQUE_MOTO, 3, r"motos?|motociclista|motoquero|casco"),
    _k(
        T.ATROPELLO,
        3,
        r"atropell\w+|embist\w+|tiro al piso|peaton|ciclista|bicicleta|monopatin"
        r"|ciclovia",
    ),
    _k(T.VUELCO, 3, r"volco|volcad[oa]|vuelco|ruedas para arriba"),
    _k(T.OBSTRUCCION_VIA, 3, r"encajad[oa]|atascad[oa]|circulacion"),
    # Defensa civil
    _k(C.DEFENSA_CIVIL, 2, r"temporal|viento|tormenta"),
    _k(T.ARBOL_CAIDO, 3, r"arbol|tipa|ramas?"),
    _k(T.ARBOL_CAIDO, 2, r"copa"),
    _k(T.FUGA_GAS, 3, r"gas"),
    _k(T.DERRUMBE, 3, r"derrumb\w+|desmoron\w+|medianera|pared|se vino abajo"),
    _k(T.DESPRENDIMIENTO, 3, r"marquesina|cartel|balcon|mamposteria|desprend\w+"),
    _k(T.INUNDACION, 3, r"inund\w+|anegad\w+|bajo nivel"),
    # Servicios públicos
    _k(T.CABLES_ELECTRICOS, 3, r"cables?|postes?|tendido"),
    _k(T.ROTURA_CANO_AGUA, 3, r"cano maestro|cano de agua|agua potable|chorro de agua"),
    _k(T.SOCAVON, 3, r"pozo|socavon|hundimiento|cloaca\w*|colector|fosa"),
    _k(T.SEMAFOROS, 3, r"semaforos?"),
    _k(T.CORTE_SUMINISTRO, 2, r"corte de luz|sin luz|se corto la luz|sin agua"),
    _k(T.ALUMBRADO, 3, r"luminaria|alumbrado|farol|lampara de la calle"),
    _k(T.PODA, 3, r"poda|podar"),
    _k(T.BACHE, 3, r"baches?"),
    # Convivencia y seguridad
    _k(C.CONVIVENCIA_SEGURIDAD, 1, r"policia|patrullero|botellas|vidriera"),
    _k(T.RINA, 3, r"pelea|rina|peleando|se estan tirando"),
    _k(T.ROBO, 3, r"robo|robando|ladron\w*|asalto|arrebato"),
    _k(T.ANIMAL_SUELTO, 3, r"perr[oa]s?|pitbull|dogo|bozal"),
    _k(T.RUIDOS, 3, r"ruidos?|musica fuerte"),
)

MAX_EVIDENCE = 3


@dataclass(frozen=True)
class _Hit:
    keyword: _Keyword
    evidence: Evidence


def read_incident(turns: Sequence[Turn], line: Line | None = None) -> IncidentReading | None:
    hits = _hits(turns)
    if not hits:
        return None
    scores: dict[Category, int] = defaultdict(int)
    for hit in hits:
        scores[hit.keyword.category] += hit.keyword.weight
    if line in LINE_PRIOR:
        prior, weight = LINE_PRIOR[line]
        scores[prior] += weight
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    category, best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    category_hits = [h for h in hits if h.keyword.category is category]
    subtype = _subtype(category_hits)
    return IncidentReading(
        category=category,
        subtype=subtype,
        evidence=_evidence(category_hits, subtype),
        runner_up=runner_up[0] if runner_up and best - runner_up[1] < CLEAR_MARGIN else None,
    )


def _hits(turns: Sequence[Turn]) -> list[_Hit]:
    hits: list[_Hit] = []
    for turn in turns:
        if turn.speaker is not Speaker.LLAMANTE:
            continue
        normalized = NormalizedTurn.of(turn)
        folded = fold(normalized.turn.text)
        for keyword in _KEYWORDS:
            for match in keyword.regex.finditer(folded):
                hits.append(_Hit(keyword, normalized.evidence(match.start(), match.end())))
    return hits


def _subtype(hits: list[_Hit]) -> Subtype | None:
    scores: dict[Subtype, int] = defaultdict(int)
    for hit in hits:
        if hit.keyword.subtype is not None:
            scores[hit.keyword.subtype] += hit.keyword.weight
    if not scores:
        return None
    return max(scores.items(), key=lambda item: item[1])[0]


def _evidence(hits: list[_Hit], subtype: Subtype | None) -> list[Evidence]:
    """The strongest phrases for the tipo, led by the best one for the subtipo, in relato order."""
    by_subtype = [h for h in hits if subtype is not None and h.keyword.subtype is subtype]
    by_weight = sorted(hits, key=lambda h: -h.keyword.weight)
    ranked = sorted(by_subtype, key=lambda h: -h.keyword.weight)[:1] + by_weight
    chosen: list[Evidence] = []
    for hit in ranked:
        ev = hit.evidence
        overlaps = any(
            c.turn_index == ev.turn_index and c.start < ev.end and ev.start < c.end for c in chosen
        )
        if not overlaps:
            chosen.append(ev)
        if len(chosen) == MAX_EVIDENCE:
            break
    return sorted(chosen, key=lambda e: (e.turn_index, e.start))
