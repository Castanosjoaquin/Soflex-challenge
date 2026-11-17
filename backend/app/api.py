"""HTTP routes under /api."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.calls.service import (
    ActionKind,
    CallNotFoundError,
    CallService,
    CannotDeriveError,
    InvalidActionError,
    InvalidActionValueError,
)
from app.catalog.demos import DemoCall
from app.catalog.incidents import SUBTYPES, TYPES, SubtypeDef, TypeDef
from app.catalog.models import CatalogCase, Category, Priority
from app.catalog.priority import PRIORITY_RULES, PriorityRule
from app.catalog.signals import SIGNALS, SignalDef
from app.config import LLMProviderName
from app.dispatch.store import DerivedCarta, DispatchStore
from app.engine.models import CallState, Line
from app.trace.models import ReadingTrace
from app.trace.narrate import TraceLine, narrate
from app.transcript.models import ParsedTurn, Speaker
from app.transcript.parser import parse_transcript

router = APIRouter(prefix="/api")


class HealthResponse(BaseModel):
    status: str
    provider: LLMProviderName
    catalog_size: int


class SampleTurn(ParsedTurn):
    """A turno ready to replay; demo calls bring their own pause, dataset ones use a default."""

    delay_ms: int | None = None


class SampleCall(BaseModel):
    """A llamada de prueba: a dataset case or a demo call, with its line and turnos to replay.

    A demo call carries the category, subcategory and priority of the dataset case it extends.
    """

    id: str
    kind: Literal["demo", "dataset"]
    title: str
    line: Line
    category: Category
    subcategory: str
    priority: Priority
    transcript: str
    turns: list[SampleTurn]


class ParseRequest(BaseModel):
    text: str = Field(max_length=20_000)


class CatalogResponse(BaseModel):
    """The closed lists the panel shows by name: señales, tipos, subtipos and the tabla."""

    signals: list[SignalDef]
    types: list[TypeDef]
    subtypes: list[SubtypeDef]
    priority_rules: list[PriorityRule]


class OpenCallRequest(BaseModel):
    line: Line
    sample_id: str | None = None


class TurnRequest(BaseModel):
    speaker: Speaker
    text: str


class ReadingDetail(BaseModel):
    """A traza as the detalle técnico shows it: told in natural language, plus the raw steps."""

    title: str
    lines: list[TraceLine]
    trace: ReadingTrace


class ActionRequest(BaseModel):
    kind: ActionKind
    target: str | None = None
    value: str | None = None
    reason: str | None = None


_LINE_BY_SOURCE = {
    "TELEFONIA_911": Line.L911,
    "TELEFONIA_107": Line.L107,
    "TELEFONIA_103": Line.L103,
    "TELEFONIA_147": Line.L147,
    "APP_CIUDADANA": Line.APP,
}


def _sample(case: CatalogCase) -> SampleCall:
    return SampleCall(
        id=case.id,
        kind="dataset",
        title=case.subcategory,
        line=_LINE_BY_SOURCE.get(case.source, Line.L911),
        category=case.category,
        subcategory=case.subcategory,
        priority=case.priority,
        transcript=case.transcript,
        turns=[
            SampleTurn(speaker=t.speaker, text=t.text) for t in parse_transcript(case.transcript)
        ],
    )


def _demo_sample(demo: DemoCall, base: CatalogCase) -> SampleCall:
    return SampleCall(
        id=demo.id,
        kind="demo",
        title=demo.title,
        line=demo.line,
        category=base.category,
        subcategory=base.subcategory,
        priority=base.priority,
        transcript=" ".join(f"{t.speaker.value.capitalize()}: {t.text}" for t in demo.turns),
        turns=[SampleTurn(speaker=t.speaker, text=t.text, delay_ms=t.delay_ms) for t in demo.turns],
    )


def _samples(request: Request) -> list[SampleCall]:
    """Demo calls first, then the dataset cases."""
    cases = _cases(request)
    by_id = {c.id: c for c in cases}
    demos: list[DemoCall] = request.app.state.demos
    return [_demo_sample(d, by_id[d.based_on]) for d in demos] + [_sample(c) for c in cases]


def _cases(request: Request) -> list[CatalogCase]:
    cases: list[CatalogCase] = request.app.state.cases
    return cases


def _calls(request: Request) -> CallService:
    calls: CallService = request.app.state.calls
    return calls


@router.get("/health")
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        provider=request.app.state.settings.effective_provider,
        catalog_size=len(_cases(request)),
    )


@router.get("/catalog")
def catalog() -> CatalogResponse:
    return CatalogResponse(
        signals=list(SIGNALS.values()),
        types=list(TYPES.values()),
        subtypes=list(SUBTYPES.values()),
        priority_rules=list(PRIORITY_RULES),
    )


@router.get("/samples")
def list_samples(request: Request) -> list[SampleCall]:
    return _samples(request)


@router.get("/samples/{case_id}")
def get_sample(case_id: str, request: Request) -> SampleCall:
    for sample in _samples(request):
        if sample.id == case_id:
            return sample
    raise HTTPException(status_code=404, detail="Caso no encontrado")


@router.post("/transcripts/parse")
def parse_pasted(body: ParseRequest) -> list[ParsedTurn]:
    """Split a pasted text into turnos, so the panel can replay it like any llamada."""
    return parse_transcript(body.text)


@router.post("/calls")
def open_call(body: OpenCallRequest, request: Request) -> CallState:
    if body.sample_id is not None and all(s.id != body.sample_id for s in _samples(request)):
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return _calls(request).open(body.line, body.sample_id)


@router.post("/calls/{call_id}/turns")
async def add_turn(call_id: str, body: TurnRequest, request: Request) -> CallState:
    try:
        return await _calls(request).add_turn(call_id, body.speaker, body.text)
    except CallNotFoundError:
        raise HTTPException(status_code=404, detail="Llamada no encontrada") from None


@router.post("/calls/{call_id}/actions")
async def act(call_id: str, body: ActionRequest, request: Request) -> CallState:
    try:
        return await _calls(request).act(call_id, body.kind, body.value, body.reason, body.target)
    except CallNotFoundError:
        raise HTTPException(status_code=404, detail="Llamada no encontrada") from None
    except InvalidActionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except InvalidActionValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/calls/{call_id}/derive")
async def derive(call_id: str, request: Request) -> CallState:
    try:
        return await _calls(request).derive(call_id)
    except CallNotFoundError:
        raise HTTPException(status_code=404, detail="Llamada no encontrada") from None
    except CannotDeriveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/calls/{call_id}/close", status_code=204)
async def close(call_id: str, request: Request) -> Response:
    try:
        await _calls(request).close(call_id)
    except CallNotFoundError:
        raise HTTPException(status_code=404, detail="Llamada no encontrada") from None
    return Response(status_code=204)


@router.get("/calls/{call_id}/readings")
def readings(call_id: str, request: Request) -> list[ReadingDetail]:
    """The traza of every lectura of the llamada, in order (SPEC §5.11)."""
    try:
        traces = _calls(request).readings(call_id)
    except CallNotFoundError:
        raise HTTPException(status_code=404, detail="Llamada no encontrada") from None
    told = [(narrate(t), t) for t in traces]
    return [ReadingDetail(title=n.title, lines=n.lines, trace=t) for n, t in told]


@router.get("/dispatch")
def dispatch(request: Request) -> list[DerivedCarta]:
    """The bandeja del despachador: Cartas derivadas, the most recent first."""
    store: DispatchStore = request.app.state.dispatch
    return store.inbox()
