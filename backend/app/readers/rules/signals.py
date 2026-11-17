"""Rules-based señales: weighted phrase patterns over the llamante's turnos (SPEC §5.3).

Each pattern proposes one value (sí, no, no se sabe) for one señal of the catalog. Patterns run
on a folded copy of the turno (lowercase, no accents, same length), so the evidence offsets are
offsets on the original text.

Negation: a "sí" pattern preceded, within its clause and its last three words, by "no", "nadie",
"sin", "ni"… reads as "no" ("No hay fuego"), and by "no sé si…" reads as "no se sabe". Patterns
that already carry their negation ("no respira", "no le entra el aire") are not negatable.

One phrase backs one señal: patterns run in order and a span already claimed is not reused
("no le entra el aire" is respira=no, not also dificultad_respirar; "se prendió fuego" is one
mention of fuego, not two). Within a señal,
the last mention in the relato wins (autocorrección: "se desmayó… recuperó la conciencia").
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.catalog.signals import SignalAnswer, SignalId
from app.readers.models import Evidence, SignalReading
from app.readers.rules.text import clause_start, extend_to_clause, fold
from app.transcript.models import Speaker, Turn

S = SignalId
SI, NO = SignalAnswer.SI, SignalAnswer.NO

_NEGATIONS = frozenset({"no", "nadie", "sin", "ni", "nunca", "tampoco", "ningun", "ninguna"})
_UNKNOWN = re.compile(r"\bno (se|sabe|sabemos|sabria decir) si\b")


@dataclass(frozen=True)
class _Pattern:
    signal: SignalId
    value: SignalAnswer
    regex: re.Pattern[str]
    negatable: bool
    extend: int
    accept: Callable[[re.Match[str]], bool] | None


def _p(
    signal: SignalId,
    pattern: str,
    value: SignalAnswer = SI,
    *,
    extend: int = 0,
    accept: Callable[[re.Match[str]], bool] | None = None,
) -> _Pattern:
    return _Pattern(
        signal=signal,
        value=value,
        regex=re.compile(pattern),
        negatable=value is SI and not pattern.startswith(r"\bno "),
        extend=extend,
        accept=accept,
    )


def _is_minor(match: re.Match[str]) -> bool:
    return int(match.group("age")) < 18


_VEHICLE = r"(auto|vehiculo|coche|camioneta|colectivo|camion|micro|tren|moto|rodado)"

# Order matters: an earlier pattern claims its phrase before a later señal can.
_PATTERNS: tuple[_Pattern, ...] = (
    # Atrapado en vehículo, before the generic persona atrapada.
    _p(
        S.ATRAPADO_VEHICULO,
        r"\b(conductor|chofer|ocupantes?|acompanante|pasajer[oa]s?)\b"
        r"[^.,;!?]{0,20}?\b(atrapad|encerrad)\w*",
    ),
    _p(
        S.ATRAPADO_VEHICULO,
        r"\bquedo (debajo|abajo|atrapad\w*|encerrad\w*) (del?|en el|en la) "
        r"(estribo|" + _VEHICLE[1:],
    ),
    _p(
        S.ATRAPADO_VEHICULO,
        r"\b(atrapad|encerrad)\w* (en|dentro de|adentro de) (el|la|un|una) " + _VEHICLE + r"\b",
    ),
    _p(S.ATRAPADO_VEHICULO, r"\bno (puede|pueden|pudo) salir del? " + _VEHICLE + r"\b"),
    # Respira / consciente: the explicit negatives first.
    _p(S.RESPIRA, r"\bno (le )?entra (el )?aire\b", NO),
    _p(S.RESPIRA, r"\bdejo de respirar\b", NO),
    _p(S.RESPIRA, r"\bno (esta )?respira(ndo)?\b", NO),
    _p(S.RESPIRA, r"\b(respira|esta respirando)\b"),
    _p(S.CONSCIENTE, r"\binconsciente\b", NO),
    _p(S.CONSCIENTE, r"\bno (responde|reacciona|contesta)\b", NO),
    _p(S.CONSCIENTE, r"\bperdio (el )?conocimiento\b", NO),
    _p(S.CONSCIENTE, r"\b(se desmayo|desmayad[oa]|se desvanecio)\b", NO),
    _p(S.CONSCIENTE, r"\brecupero (la )?(conciencia|consciencia|conocimiento)\b"),
    _p(S.CONSCIENTE, r"\b(esta )?consciente\b"),
    _p(S.CONSCIENTE, r"\b(esta hablando|me habla|habla bien)\b"),
    # Persona atrapada.
    _p(S.PERSONA_ATRAPADA, r"\bno (quedo|queda|hay|habia) nadie\b( adentro| atrapad\w*)?", NO),
    _p(S.PERSONA_ATRAPADA, r"\b(adentro|dentro) (quedo|quedaron)( \w+){1,3}"),
    _p(
        S.PERSONA_ATRAPADA,
        r"\b(quedo|quedaron|queda|quedan) (alguien |gente |una persona "
        r"|\w+ personas )?(adentro|atrapad\w*|encerrad\w*)\b",
    ),
    _p(
        S.PERSONA_ATRAPADA,
        r"\bhay (\w+ )?(personas?|gente|alguien) (adentro|atrapad\w*"
        r"|encerrad\w*)\b",
    ),
    _p(S.PERSONA_ATRAPADA, r"\b(esta|estan|siguen|sigue) (atrapad|encerrad)\w*"),
    _p(S.PERSONA_ATRAPADA, r"\b(atrapad|encerrad)[oa]s?\b"),
    _p(S.PERSONA_ATRAPADA, r"\besperando (el |ser )?rescat\w*"),
    # Fuego, humo, explosión.
    _p(S.FUEGO_ACTIVO, r"\b(se prendio|prendieron|prendio) fuego\b", extend=40),
    _p(S.FUEGO_ACTIVO, r"\b(fuego|llamas|llamarada|incendio|se esta quemando|quema)\b"),
    _p(S.HUMO, r"\bhumo\b", extend=25),
    _p(S.EXPLOSION, r"\b(explot\w+( una| un| la| el)? \w+|explosion( \w+)?|estall\w+)"),
    # Gas, combustible, electricidad.
    _p(
        S.GAS,
        r"\b(olor a gas|fuga de gas|perdida de gas|escape de gas|cano de gas|garrafas?"
        r"|gas)\b",
    ),
    _p(
        S.DERRAME_COMBUSTIBLE,
        r"\b(perdiendo|pierde|perdida de|derrama\w*|derrame de|chorrea\w*) "
        r"(gasoil|nafta|combustible|aceite|gasolina)\b",
        extend=30,
    ),
    _p(S.DERRAME_COMBUSTIBLE, r"\b(gasoil|nafta|combustible)\b"),
    _p(
        S.CABLES_CAIDOS,
        r"\b(corto|cortaron|arranco|arrancaron|tiro|tiraron|enganch\w+)"
        r"( \w+){0,3} (cables?|postes?)\b",
    ),
    _p(S.CABLES_CAIDOS, r"\bcables? (cortad|caid|suelt|colgand|tirad)\w*"),
    _p(
        S.RIESGO_ELECTRICO,
        r"\b(chispe\w+|chispas|descargas?( electricas?)?|electrocut\w*"
        r"|cortocircuito|tablero( electrico| central)?|subestacion electrica"
        r"|cables? (pelados?|con corriente|electrificad\w*))\b",
    ),
    # Violencia.
    _p(
        S.ARMA_FUEGO,
        r"\b(arma de fuego|pistolas?|revolver|escopeta|tiros|tiroteo|balazos?"
        r"|balead[oa]s?)\b",
    ),
    _p(S.ARMA_FUEGO, r"\bdisparos?\b(?! de (salbutamol|inhalador|puf))"),
    _p(
        S.ARMA_BLANCA,
        r"\b(cuchillos?|navajas?|punal\w*|arma blanca|apunal\w+|acuchill\w+"
        r"|machete)\b",
    ),
    _p(
        S.INVOLUCRADOS_EN_LUGAR,
        r"\b(se fueron|se escaparon|huyeron|se dieron a la fuga"
        r"|se escapo|se fue)\b",
        NO,
    ),
    _p(S.INVOLUCRADOS_EN_LUGAR, r"\bse (estan|siguen) (peleando|tirando|pegando|agarrando)\b"),
    _p(
        S.INVOLUCRADOS_EN_LUGAR,
        r"\b(siguen|sigue|todavia esta\w*) (aca|ahi|en el lugar"
        r"|peleando)\b",
    ),
    _p(S.INVOLUCRADOS_EN_LUGAR, r"\b(hay una pelea|estan peleando)\b"),
    _p(
        S.ANIMAL_MORDEDURA,
        r"\b(perr[oa]|gato|animal|pitbull|dogo)s?\b[^.;!?]{0,60}?"
        r"\b(mordi\w+|atac\w+)",
    ),
    _p(S.ANIMAL_MORDEDURA, r"\b(mordid[oa]|mordedura)\b"),
    # Cuerpo.
    _p(S.SANGRADO_ABUNDANTE, r"\bsangr\w+ (mucho|muchisimo|abundante\w*|a chorros|sin parar)\b"),
    _p(S.SANGRADO_ABUNDANTE, r"\b(mucha sangre|hemorragia|charco de sangre)\b"),
    _p(
        S.DIFICULTAD_RESPIRAR,
        r"\b(le cuesta|no puede|dificultad para|problemas? para) "
        r"respirar\b",
    ),
    _p(S.DIFICULTAD_RESPIRAR, r"\bse (le )?(esta )?(cierra|cerrando) la garganta\b"),
    _p(S.DIFICULTAD_RESPIRAR, r"\b(le falta el aire|falta de aire|se ahoga\w*|ahogando)\b"),
    _p(
        S.DIFICULTAD_RESPIRAR,
        r"\b(tiraje( en las costillas)?|labios morados|broncoespasmo"
        r"|crisis (de )?asma\w*)\b",
    ),
    _p(S.GOLPE_CABEZA, r"\b(golpe\w*|pego|se dio)( \w+){0,4} (en )?(la )?cabeza\b"),
    _p(S.GOLPE_CABEZA, r"\b(traumatismo de craneo|cayo de cabeza)\b"),
    _p(S.HERIDOS, r"\b(herid[oa]s?|lesionad[oa]s?|lastimad[oa]s?|fractura\w*|raspon\w*)\b"),
    _p(S.HERIDOS, r"\b(sal\w+ )?mareada?s?\b"),
    _p(S.HERIDOS, r"\ble duele( mucho)?( la| el)? \w+"),
    _p(S.HERIDOS, r"\b(llora|llorando|grita|gritando) de dolor\b"),
    _p(S.HERIDOS, r"\bno (se )?puede mover (la|el) \w+"),
    _p(
        S.MENORES,
        r"\b(nenes?|nenas?|bebes?|ninos?|ninas?|chicos|chiquit[oa]s?|criaturas?"
        r"|menor(es)? de edad)\b",
    ),
    _p(
        S.MENORES,
        r"\b(hij[oa]|nene|nena|chic[oa]|nin[oa]) de (?P<age>\d{1,2}) anos\b",
        accept=_is_minor,
    ),
    _p(S.MOTOCICLISTA, r"\b(motos?|motociclistas?|motoqueros?)\b"),
    # Escenario.
    _p(
        S.EVACUADO,
        r"\b(salieron todos|salimos todos|ya salimos|ya salieron|estan todos afuera"
        r"|estamos (todos )?afuera|evacuad[oa]s?|evacuaron)\b",
    ),
    _p(
        S.PROPAGACION,
        r"\b(ya )?entra\w* a (las|los) (casas|departamentos|vecinos|edificios"
        r"|pisos)\b",
    ),
    _p(
        S.PROPAGACION,
        r"\b(se (esta |estan )?(propaga\w*|extiende\w*|expande\w*|agranda\w*"
        r"|metiendo)|avanza\w*( hacia)?|linderos?)\b",
    ),
    _p(
        S.AGUA_SUBE,
        r"\b(el )?agua (sube|esta subiendo|sigue subiendo|llega|entra"
        r"|esta entrando)\b",
    ),
    _p(S.AGUA_SUBE, r"\b(esta )?entrando agua\b"),
    _p(S.AGUA_SUBE, r"\b(se inundo|se esta inundando|inunda\w*)\b"),
    _p(
        S.ESTRUCTURA_CEDE,
        r"\b(derrumb\w+|desmoron\w+|se (vino|cayo) abajo|colaps\w+"
        r"|se desprend\w+|socavon|se abrio un pozo|hundimiento|se hundio|grietas?|cediendo"
        r"|riesgo de (seguir )?ca\w+|balanceandose)\b",
    ),
)


@dataclass(frozen=True)
class _Hit:
    turn_index: int
    start: int
    end: int
    signal: SignalId
    value: SignalAnswer


def read_signals(turns: Sequence[Turn]) -> list[SignalReading]:
    """The señales the llamante's turnos affirm, deny or leave open: the last mention wins."""
    latest: dict[SignalId, tuple[_Hit, Evidence]] = {}
    for turn in turns:
        if turn.speaker is not Speaker.LLAMANTE:
            continue
        for hit in _read_turn(turn):
            evidence = Evidence(
                turn_index=hit.turn_index,
                start=hit.start,
                end=hit.end,
                quote=turn.text[hit.start : hit.end],
            )
            previous = latest.get(hit.signal)
            if previous is None or (hit.turn_index, hit.start) >= (
                previous[0].turn_index,
                previous[0].start,
            ):
                latest[hit.signal] = (hit, evidence)
    return [
        SignalReading(signal_id=signal, value=latest[signal][0].value, evidence=latest[signal][1])
        for signal in SignalId
        if signal in latest
    ]


def _read_turn(turn: Turn) -> list[_Hit]:
    folded = fold(turn.text)
    hits: list[_Hit] = []
    for pattern in _PATTERNS:
        for match in pattern.regex.finditer(folded):
            if pattern.accept is not None and not pattern.accept(match):
                continue
            start, value = _qualify(folded, match.start(), pattern)
            end = match.end()
            if pattern.extend:
                end = extend_to_clause(folded, start, end, pattern.extend)
            if any(_overlaps(h, start, end) for h in hits):
                continue
            hits.append(_Hit(turn.index, start, end, pattern.signal, value))
    return hits


def _qualify(folded: str, start: int, pattern: _Pattern) -> tuple[int, SignalAnswer]:
    """Apply a negation or a "no sé si" that precedes the match within its clause."""
    if not pattern.negatable:
        return start, pattern.value
    head_start = clause_start(folded, start)
    head = folded[head_start:start]
    unknowns = list(_UNKNOWN.finditer(head))
    if unknowns and len(head[unknowns[-1].end() :].split()) <= 2:
        return head_start + unknowns[-1].start(), SignalAnswer.NO_SABE
    for word in list(re.finditer(r"\S+", head))[-3:]:
        if word.group() in _NEGATIONS:
            return head_start + word.start(), NO
    return start, pattern.value


def _overlaps(hit: _Hit, start: int, end: int) -> bool:
    return hit.start < end and start < hit.end
