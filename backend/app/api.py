"""HTTP routes under /api."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.calls.service import (
    ActionKind,
    CallNotFoundError,
    CallService,
    CannotDeriveError,
    InvalidActionError,
    InvalidActionValueError,
)
from app.catalog.incidents import SUBTYPES, TYPES, SubtypeDef, TypeDef
from app.catalog.models import CatalogCase, Category, Priority
from app.catalog.priority import PRIORITY_RULES, PriorityRule
from app.catalog.signals import SIGNALS, SignalDef
from app.config import LLMProviderName
from app.dispatch.store import DerivedCarta, DispatchStore
from app.engine.models import CallState, Line
from app.transcript.models import ParsedTurn, Speaker
from app.transcript.parser import parse_transcript

router = APIRouter(prefix="/api")


class HealthResponse(BaseModel):
    status: str
    provider: LLMProviderName
    catalog_size: int


class SampleCall(BaseModel):
    """A dataset case as a llamada de prueba: its line and its turnos, ready to replay."""

    id: str
    line: Line
    category: Category
    subcategory: str
    priority: Priority
    transcript: str
    turns: list[ParsedTurn]


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
        line=_LINE_BY_SOURCE.get(case.source, Line.L911),
        category=case.category,
        subcategory=case.subcategory,
        priority=case.priority,
        transcript=case.transcript,
        turns=parse_transcript(case.transcript),
    )


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
    return [_sample(c) for c in _cases(request)]


@router.get("/samples/{case_id}")
def get_sample(case_id: str, request: Request) -> SampleCall:
    for case in _cases(request):
        if case.id == case_id:
            return _sample(case)
    raise HTTPException(status_code=404, detail="Caso no encontrado")


@router.post("/calls")
def open_call(body: OpenCallRequest, request: Request) -> CallState:
    if body.sample_id is not None and all(c.id != body.sample_id for c in _cases(request)):
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


@router.get("/dispatch")
def dispatch(request: Request) -> list[DerivedCarta]:
    """The bandeja del despachador: Cartas derivadas, the most recent first."""
    store: DispatchStore = request.app.state.dispatch
    return store.inbox()
