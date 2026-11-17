"""Runtime configuration, read from environment variables (see .env.example)."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class LLMProviderName(StrEnum):
    MOCK = "mock"
    OPENAI_COMPAT = "openai_compat"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: LLMProviderName = LLMProviderName.MOCK
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: float = 20.0

    dataset_path: Path = REPO_ROOT / "data" / "dataset_challenge_soflex.csv"
    demo_calls_dir: Path = REPO_ROOT / "data" / "demo_calls"
    database_path: Path = REPO_ROOT / "var" / "copiloto.db"
    static_dir: Path = REPO_ROOT / "frontend" / "dist"

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value: object) -> object:
        # docker compose passes LLM_API_KEY="" when unset; treat it as "no credentials".
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def effective_provider(self) -> LLMProviderName:
        """Fall back to the deterministic mock when no credentials are configured."""
        if self.llm_provider is LLMProviderName.OPENAI_COMPAT and self.llm_api_key is None:
            return LLMProviderName.MOCK
        return self.llm_provider


@lru_cache
def get_settings() -> Settings:
    return Settings()
