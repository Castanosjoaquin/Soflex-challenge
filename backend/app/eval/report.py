"""The evaluación as a Markdown table (SPEC §8), from the saved result of each modo.

Each run saves its outcomes in ``data/eval/results/<provider>.json``; the report is rebuilt from
every result there, so the IA column stays "pendiente" until that run exists.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel

from app.config import LLMProviderName
from app.eval.corpus import ORIGINAL
from app.eval.metrics import Confusion, Rate, rate
from app.eval.noise import SEED, NoiseKind
from app.eval.runner import Outcome


class RunResult(BaseModel):
    provider: LLMProviderName
    model: str | None = None
    seed: int = SEED
    outcomes: list[Outcome]


def result_path(results_dir: Path, provider: LLMProviderName) -> Path:
    return results_dir / f"{provider.value}.json"


def save(result: RunResult, results_dir: Path) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = result_path(results_dir, result.provider)
    path.write_text(result.model_dump_json(indent=1) + "\n", encoding="utf-8")
    return path


def load(results_dir: Path, provider: LLMProviderName) -> RunResult | None:
    path = result_path(results_dir, provider)
    if not path.exists():
        return None
    return RunResult.model_validate_json(path.read_text(encoding="utf-8"))


# --- Metrics over a set of outcomes --------------------------------------------------------------


def _confusion(outcomes: Sequence[Outcome]) -> Confusion:
    total = Confusion()
    for o in outcomes:
        total += o.confusion
    return total


Metric = Callable[[Sequence[Outcome]], Rate]

METRICS: tuple[tuple[str, Metric, bool], ...] = (
    # label, metric, only with the IA
    ("Calle (nombre oficial)", lambda os: rate(o.street_ok for o in os), False),
    ("Altura", lambda os: rate(o.altura_ok for o in os), False),
    ("Tipo", lambda os: rate(o.category_ok for o in os), False),
    ("Prioridad", lambda os: rate(o.priority_ok for o in os), False),
    ("Pre-marcas · precisión", lambda os: _confusion(os).precision, False),
    ("Pre-marcas · recall", lambda os: _confusion(os).recall, False),
    (
        "Datos descartados antes del filtro",
        lambda os: Rate(sum(o.discarded for o in os), sum(o.proposed for o in os)),
        False,
    ),
    (
        "Respuestas rotas de la IA",
        lambda os: Rate(sum(o.broken for o in os), sum(o.lecturas for o in os)),
        True,
    ),
    (
        "Fallbacks a reglas",
        lambda os: Rate(sum(o.fallbacks for o in os), sum(o.lecturas for o in os)),
        True,
    ),
)


def _pct(r: Rate) -> str:
    value = r.value
    return "—" if value is None else f"{r.hits}/{r.total} · {value:.0%}".replace("%", " %")


def _delta(before: Rate, after: Rate) -> str:
    if before.value is None or after.value is None:
        return "—"
    pp = round((after.value - before.value) * 100)
    return f"{pp:+d} pp".replace("-", "\N{MINUS SIGN}") if pp else "0 pp"


def _split(outcomes: Sequence[Outcome]) -> tuple[list[Outcome], list[Outcome]]:
    original = [o for o in outcomes if o.variant == ORIGINAL]
    return original, [o for o in outcomes if o.variant != ORIGINAL]


# --- Markdown ------------------------------------------------------------------------------------

_MODES = ((LLMProviderName.MOCK, "Simulado"), (LLMProviderName.OPENAI_COMPAT, "IA"))
_COMMAND = "uv run python -m app.eval --provider {provider}"
_IA_COMMAND = (
    "cd backend && LLM_PROVIDER=openai_compat LLM_API_KEY=<clave> "
    "uv run python -m app.eval --provider openai_compat"
)


def render(results: dict[LLMProviderName, RunResult | None]) -> str:
    n = _n_cases(results)
    kinds = len(NoiseKind)
    one_case = f"{100 / n:.1f}".replace(".", ",")
    lines = [
        "# Evaluación del copiloto",
        "",
        f"> **Con n = {n} no se puede afirmar nada estadísticamente.** Un caso mueve "
        f"{one_case} puntos y ninguna diferencia de estas tablas es significativa: sirven para "
        "ver dónde falla "
        "el copiloto, no para decir que un modo es mejor que otro. Además, las reglas y el "
        "catálogo se escribieron mirando estos mismos 30 casos (EDA §8): los números del "
        "original son optimistas, y las variantes ruidosas son la medida más honesta.",
        "",
        f"Corpus: las {n} llamadas del dataset tal como vienen (*original*) y {kinds} variantes "
        f"ruidosas de cada una (*ruidoso*, {n * kinds} llamadas, semilla {SEED}, en "
        "`data/eval/noisy/`). Se genera con `uv run python -m app.eval.noise` y se corre con "
        "`uv run python -m app.eval [--provider mock|openai_compat]` desde `backend/`.",
        "",
        "## Resultados",
        "",
        "| Métrica | "
        + " | ".join(f"{label} · original | {label} · ruidoso | Δ" for _, label in _MODES)
        + " |",
        "|---|" + "--:|--:|--:|" * len(_MODES),
    ]
    for label, metric, ia_only in METRICS:
        cells = []
        for provider, _ in _MODES:
            result = results.get(provider)
            if result is None:
                cells += ["pendiente", "pendiente", "—"]
            elif ia_only and provider is LLMProviderName.MOCK:
                cells += ["— (sin IA)", "— (sin IA)", "—"]
            else:
                original, noisy = _split(result.outcomes)
                before, after = metric(original), metric(noisy)
                cells += [_pct(before), _pct(after), _delta(before, after)]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    for provider, label in _MODES:
        lines += ["", f"## Degradación por tipo de ruido · {label}", ""]
        result = results.get(provider)
        if result is None:
            lines += _pending(provider)
            continue
        if result.model:
            lines += [f"Modelo: `{result.model}`.", ""]
        lines += _by_kind(result.outcomes)

    lines += ["", *_HOW]
    return "\n".join(lines) + "\n"


def _n_cases(results: dict[LLMProviderName, RunResult | None]) -> int:
    for result in results.values():
        if result is not None:
            return len({o.case_id for o in result.outcomes})
    return 30


def _by_kind(outcomes: Sequence[Outcome]) -> list[str]:
    columns = ("Calle", "Altura", "Tipo", "Prioridad", "Pre-marcas P", "Pre-marcas R")
    metrics: tuple[Metric, ...] = (
        lambda os: rate(o.street_ok for o in os),
        lambda os: rate(o.altura_ok for o in os),
        lambda os: rate(o.category_ok for o in os),
        lambda os: rate(o.priority_ok for o in os),
        lambda os: _confusion(os).precision,
        lambda os: _confusion(os).recall,
    )
    lines = [
        "| Variante | Con ruido | " + " | ".join(columns) + " |",
        "|---|--:|" + "--:|" * len(columns),
    ]
    for variant in (ORIGINAL, *(k.value for k in NoiseKind)):
        subset = [o for o in outcomes if o.variant == variant]
        if not subset:
            continue
        applied = "—" if variant == ORIGINAL else f"{sum(o.applied for o in subset)}/{len(subset)}"
        cells = [_count(m(subset)) for m in metrics]
        lines.append(f"| {variant} | {applied} | " + " | ".join(cells) + " |")
    return lines


def _count(r: Rate) -> str:
    return "—" if r.total == 0 else f"{r.hits}/{r.total}"


def _pending(provider: LLMProviderName) -> list[str]:
    if provider is LLMProviderName.MOCK:
        return [f"Pendiente: `{_COMMAND.format(provider=provider.value)}`."]
    return [
        "**Pendiente.** Esta tabla se generó sin `LLM_API_KEY`, así que no hay corrida con IA y "
        "no se inventan sus números. Para completarla (el resultado se guarda en "
        "`data/eval/results/openai_compat.json` y esta tabla se regenera con las dos columnas):",
        "",
        "```sh",
        _IA_COMMAND,
        "```",
        "",
        "`LLM_BASE_URL` y `LLM_MODEL` eligen el endpoint compatible con OpenAI (por defecto, Groq "
        "con `llama-3.3-70b-versatile`). `--concurrency` limita las llamadas simultáneas.",
    ]


_HOW = [
    "## Cómo se mide",
    "",
    "- **Calle**: el nombre oficial al que llega el copiloto contra el nombre oficial de "
    "`calle_detectada` (los dos por el mismo matcher de calles).",
    "- **Altura**: el número leído contra `altura_detectada` cuando es un número solo. Cuando "
    'trae una nota ("4500 (esquina)", "Km 7 (altura Parque Norte)", "S/N (…)") el relato no '
    "dice ningún número (EDA §7): el acierto es no leer altura.",
    "- **Tipo** y **prioridad**: contra `categoria` y `prioridad_sugerida`.",
    "- **Pre-marcas**: por cada mandatoria de la anotación manual que responde una señal del "
    "catálogo (`data/eval/mandatorias_senales.csv`), si el copiloto conoce esa señal contra si "
    "el relato la responde (A o P en la anotación). Las mandatorias que ninguna señal responde "
    "(antecedentes, tiempo de crisis, carriles…) no se pueden pre-marcar y quedan afuera. No mide "
    "si el valor (sí/no) es el correcto: la anotación no lo trae.",
    "- **Datos descartados**: de los datos que propone el lector (ubicación, tipo, cada señal), "
    "los que se tiran por no tener evidencia en el relato o por estar fuera de las listas. En "
    "simulado es el lector por reglas; con IA, el lector con IA (la tasa de alucinación antes "
    "del filtro).",
    "- **Respuestas rotas**: lecturas de la IA cuya respuesta no era válida tal como llegó "
    "(reparada, reintentada o abandonada). **Fallbacks**: lecturas que terminaron solo con "
    "reglas (respuesta inválida tras el reintento, timeout o error del proveedor).",
    "- **Ruidoso**: las variantes juntas. En `sin_direccion` el gold de calle y altura es "
    '"ninguna": acierta si el copiloto no inventa una. El resto del gold es el del original.',
    "- Una lectura por cada turno del llamante, sin acciones del operador.",
]
