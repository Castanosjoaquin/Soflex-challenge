from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.catalog.loader import parse_dataset
from app.catalog.models import Category
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


def test_dataset_parses_all_cases() -> None:
    cases = parse_dataset(DATASET)
    assert len(cases) == 30
    assert {c.category for c in cases} == set(Category)
    assert all(c.mandatory_questions for c in cases)


def test_health_reports_mock_provider(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body == {"status": "ok", "provider": "mock", "catalog_size": 30}


def test_samples_roundtrip(client: TestClient) -> None:
    samples = client.get("/api/samples").json()
    assert len(samples) == 30
    first = client.get(f"/api/samples/{samples[0]['id']}").json()
    assert first == samples[0]
    assert client.get("/api/samples/NOPE").status_code == 404


@pytest.mark.parametrize("key", [None, "", "   "])
def test_openai_compat_without_key_falls_back_to_mock(key: str | None) -> None:
    settings = Settings.model_validate(
        {"llm_provider": LLMProviderName.OPENAI_COMPAT, "llm_api_key": key}
    )
    assert settings.effective_provider is LLMProviderName.MOCK
