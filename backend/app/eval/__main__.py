"""`uv run python -m app.eval [--provider mock|openai_compat]`: run the evaluación (SPEC §8).

Replays the corpus in the chosen modo, saves its outcomes in ``data/eval/results/`` and rewrites
``data/eval/resultados.md`` with every modo that has a result. Not part of pytest: it is a report,
not a gate.
"""

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence

from app.config import LLMProviderName, Settings
from app.engine.models import Line
from app.eval import report
from app.eval.corpus import EVAL_DIR, load_corpus
from app.eval.runner import run_corpus
from app.readers.ia.provider import OpenAICompatProvider
from app.readers.ia.reader import IAReader, IAReading
from app.transcript.models import Turn

RESULTS_DIR = EVAL_DIR / "results"
REPORT_PATH = EVAL_DIR / "resultados.md"


def _args(settings: Settings) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.eval", description=__doc__)
    parser.add_argument(
        "--provider",
        type=LLMProviderName,
        choices=list(LLMProviderName),
        default=settings.llm_provider,
        help="mock: solo el lector por reglas · openai_compat: reglas más el lector con IA "
        "(por defecto, LLM_PROVIDER)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="llamadas a la IA en paralelo (por defecto, 4)",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.0,
        help="segundos mínimos entre lecturas con IA, para no pasar el límite de tokens por "
        "minuto de un plan gratuito (por defecto, 0)",
    )
    return parser.parse_args()


class _PacedIAReader(IAReader):
    """An IAReader that waits its turn *before* the lectura starts, never inside it.

    The wait stays out of the lectura's timeout: a rate limit of the plan is not a slow IA. Only
    for the evaluación; the copiloto never waits.
    """

    def __init__(self, inner: IAReader, pause: float) -> None:
        self._inner = inner
        self._pause = pause
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def read(self, turns: Sequence[Turn], line: Line | None = None) -> IAReading:
        async with self._lock:
            wait = self._next - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._next = time.monotonic() + self._pause
        return await self._inner.read(turns, line)


async def _run(
    settings: Settings, provider: LLMProviderName, concurrency: int, pause: float
) -> None:
    ia_provider = None
    if provider is LLMProviderName.OPENAI_COMPAT:
        if settings.llm_api_key is None:
            sys.exit("--provider openai_compat necesita LLM_API_KEY (y LLM_BASE_URL, LLM_MODEL)")
        ia_provider = OpenAICompatProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key.get_secret_value(),
            timeout_seconds=settings.llm_timeout_seconds,
        )
    ia = IAReader(ia_provider, settings.llm_timeout_seconds) if ia_provider else None
    if ia is not None and pause > 0:
        ia = _PacedIAReader(ia, pause)
    started = time.monotonic()
    try:
        outcomes = await run_corpus(load_corpus(), ia, concurrency)
    finally:
        if ia_provider is not None:
            await ia_provider.aclose()
    elapsed = time.monotonic() - started

    result = report.RunResult(
        provider=provider,
        model=ia_provider.model if ia_provider else None,
        outcomes=outcomes,
    )
    report.save(result, RESULTS_DIR)
    markdown = report.render({p: report.load(RESULTS_DIR, p) for p in LLMProviderName})
    REPORT_PATH.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"{len(outcomes)} llamadas en {elapsed:.1f} s · {REPORT_PATH}", file=sys.stderr)


def main() -> None:
    settings = Settings()
    args = _args(settings)
    asyncio.run(_run(settings, args.provider, args.concurrency, args.pause))


if __name__ == "__main__":
    main()
