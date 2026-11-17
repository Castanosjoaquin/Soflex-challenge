"""FastAPI entrypoint: seeds the catalog, mounts the API and serves the built panel."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.catalog.loader import load_cases, parse_dataset, seed_database
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        seed_database(settings.database_path, parse_dataset(settings.dataset_path))
        app.state.cases = load_cases(settings.database_path)
        yield

    app = FastAPI(title="Copiloto de Sala", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(router)

    if settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="panel")

    return app


app = create_app()
