"""A fake OpenAI-compatible endpoint: it answers each request with the next scripted reply."""

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import httpx

from app.readers.ia.provider import OpenAICompatProvider
from app.readers.ia.reader import IAReader

SLOW = object()  # a reply that never arrives in time


class FakeEndpoint:
    def __init__(self, replies: Sequence[object]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        reply = self.replies.pop(0)
        if reply is SLOW:
            await asyncio.sleep(10)
        if isinstance(reply, httpx.Response):
            return reply
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def ia_reader(endpoint: FakeEndpoint, timeout_seconds: float = 8.0) -> IAReader:
    client = httpx.AsyncClient(transport=httpx.MockTransport(endpoint))
    provider = OpenAICompatProvider(
        base_url="https://fake.test/v1",
        model="fake-model",
        api_key="test-key",
        timeout_seconds=timeout_seconds,
        client=client,
    )
    return IAReader(provider, timeout_seconds)
