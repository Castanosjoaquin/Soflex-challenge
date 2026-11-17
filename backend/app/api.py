"""HTTP routes under /api."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.catalog.models import CatalogCase, Category, Priority
from app.config import LLMProviderName

router = APIRouter(prefix="/api")


class HealthResponse(BaseModel):
    status: str
    provider: LLMProviderName
    catalog_size: int


class SampleCall(BaseModel):
    """Lightweight view of a dataset case, used to load test transcripts in the panel."""

    id: str
    category: Category
    subcategory: str
    priority: Priority
    transcript: str


def _cases(request: Request) -> list[CatalogCase]:
    cases: list[CatalogCase] = request.app.state.cases
    return cases


@router.get("/health")
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        provider=request.app.state.settings.effective_provider,
        catalog_size=len(_cases(request)),
    )


@router.get("/samples")
def list_samples(request: Request) -> list[SampleCall]:
    return [SampleCall.model_validate(c, from_attributes=True) for c in _cases(request)]


@router.get("/samples/{case_id}")
def get_sample(case_id: str, request: Request) -> SampleCall:
    for case in _cases(request):
        if case.id == case_id:
            return SampleCall.model_validate(case, from_attributes=True)
    raise HTTPException(status_code=404, detail="Caso no encontrado")
