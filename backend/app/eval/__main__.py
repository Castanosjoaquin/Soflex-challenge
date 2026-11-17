"""`uv run python -m app.eval [--provider mock|openai_compat]`: run the evaluación (SPEC §8).

Replays the corpus in the chosen modo, saves its outcomes in ``data/eval/results/`` and rewrites
``data/eval/resultados.md`` with every modo that has a result. Not part of pytest: it is a report,
not a gate.
"""

import argparse
import asyncio
import sys
import time

from app.config import LLMProviderName, Settings
from app.eval import report
from app.eval.corpus import EVAL_DIR, load_corpus
from app.eval.runner import run_corpus
from app.readers.ia.provider import OpenAICompatProvider
from app.readers.ia.reader import IAReader

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
    return parser.parse_args()


async def _run(settings: Settings, provider: LLMProviderName, concurrency: int) -> None:
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
    asyncio.run(_run(settings, args.provider, args.concurrency))


if __name__ == "__main__":
    main()
