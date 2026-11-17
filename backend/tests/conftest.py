from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, LLMProviderName, Settings
from app.main import create_app

DATASET = REPO_ROOT / "data" / "dataset_challenge_soflex.csv"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        llm_provider=LLMProviderName.MOCK,
        dataset_path=DATASET,
        database_path=tmp_path / "test.db",
        static_dir=tmp_path / "no-static",
    )
    with TestClient(create_app(settings)) as c:
        yield c
