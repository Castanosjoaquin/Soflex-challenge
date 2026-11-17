"""FastAPI entrypoint: seeds the catalog, mounts the API and serves the built panel."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.calls.action_log import ActionLog
from app.calls.service import CallService
from app.catalog.loader import load_cases, parse_dataset, seed_database
from app.config import LLMProviderName, Settings, get_settings
from app.dispatch.store import DispatchStore
from app.engine.models import Mode
from app.readers.rules.reader import RulesReader


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        seed_database(settings.database_path, parse_dataset(settings.dataset_path))
        app.state.cases = load_cases(settings.database_path)
        app.state.action_log = ActionLog(settings.database_path)
        # The Lector con IA arrives with its own ticket; until then every llamada runs on rules.
        mode = Mode.SIMULADO if settings.effective_provider is LLMProviderName.MOCK else Mode.REGLAS
        app.state.dispatch = DispatchStore(settings.database_path)
        app.state.calls = CallService(RulesReader(), app.state.action_log, app.state.dispatch, mode)
        yield

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


app = create_app()
