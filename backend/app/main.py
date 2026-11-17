"""FastAPI entrypoint: seeds the catalog, mounts the API and serves the built panel."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.calls.action_log import ActionLog
from app.calls.service import CallService
from app.catalog.demos import load_demo_calls
from app.catalog.loader import load_cases, parse_dataset, seed_database
from app.config import LLMProviderName, Settings, get_settings
from app.dispatch.store import DispatchStore
from app.engine.models import Mode
from app.readers.ia.provider import OpenAICompatProvider
from app.readers.ia.reader import IAReader
from app.readers.rules.reader import RulesReader


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        seed_database(settings.database_path, parse_dataset(settings.dataset_path))
        app.state.cases = load_cases(settings.database_path)
        app.state.demos = load_demo_calls(settings.demo_calls_dir, {c.id for c in app.state.cases})
        app.state.action_log = ActionLog(settings.database_path)
        app.state.dispatch = DispatchStore(settings.database_path)
        provider = _provider(settings)
        ia_reader = IAReader(provider, settings.llm_timeout_seconds) if provider else None
        app.state.calls = CallService(
            RulesReader(),
            app.state.action_log,
            app.state.dispatch,
            Mode.SIMULADO if provider is None else Mode.IA,
            ia_reader=ia_reader,
        )
        yield
        if provider is not None:
            await provider.aclose()

    app = FastAPI(title="Copiloto de Sala", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(router)

    if settings.static_dir.is_dir():
        index = settings.static_dir / "index.html"

        # Routes of the panel (SPA): reloading them must serve the panel, not a 404.
        @app.get("/despacho", include_in_schema=False)
        def despacho() -> FileResponse:
            return FileResponse(index)

        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="panel")

    return app


def _provider(settings: Settings) -> OpenAICompatProvider | None:
    """The Lector con IA's proveedor, or None in modo simulado (no credentials, or `mock`)."""
    if settings.effective_provider is not LLMProviderName.OPENAI_COMPAT or not settings.llm_api_key:
        return None
    return OpenAICompatProvider(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key.get_secret_value(),
        timeout_seconds=settings.llm_timeout_seconds,
    )


app = create_app()
