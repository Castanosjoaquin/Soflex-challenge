"""The `openai_compat` proveedor: one chat completion over httpx, asking for a JSON object.

Works with any OpenAI-compatible endpoint: Groq, Gemini (its OpenAI endpoint) and Ollama. The
`httpx.AsyncClient` can be injected, so tests replace the network with a fake transport.
"""

from typing import Any

import httpx


class ProviderError(RuntimeError):
    """The proveedor did not answer with a completion (HTTP error, network, empty answer)."""


class OpenAICompatProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    @property
    def model(self) -> str:
        return self._model

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """The text of the first choice. Raises `ProviderError` when there is none."""
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            response = await self._client.post(self._url, json=body, headers=self._headers)
        except httpx.TimeoutException:
            raise  # a timeout is its own fallback reason
        except httpx.HTTPError as exc:
            raise ProviderError(f"{type(exc).__name__}: {exc}") from None
        if response.status_code != 200:
            raise ProviderError(f"HTTP {response.status_code}: {response.text[:200]}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError(f"Respuesta sin completion: {response.text[:200]}") from None
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("Completion vacía")
        return content

    async def aclose(self) -> None:
        await self._client.aclose()
