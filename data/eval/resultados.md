# Evaluación del copiloto

> **Con n = 30 no se puede afirmar nada estadísticamente.** Un caso mueve 3,3 puntos y ninguna diferencia de estas tablas es significativa: sirven para ver dónde falla el copiloto, no para decir que un modo es mejor que otro. Además, las reglas y el catálogo se escribieron mirando estos mismos 30 casos (EDA §8): los números del original son optimistas, y las variantes ruidosas son la medida más honesta.

Corpus: las 30 llamadas del dataset tal como vienen (*original*) y 7 variantes ruidosas de cada una (*ruidoso*, 210 llamadas, semilla 13, en `data/eval/noisy/`). Se genera con `uv run python -m app.eval.noise` y se corre con `uv run python -m app.eval [--provider mock|openai_compat]` desde `backend/`.

## Resultados

| Métrica | Simulado · original | Simulado · ruidoso | Δ | IA · original | IA · ruidoso | Δ |
|---|--:|--:|--:|--:|--:|--:|
| Calle (nombre oficial) | 28/30 · 93 % | 165/210 · 79 % | −15 pp | pendiente | pendiente | — |
| Altura | 29/30 · 97 % | 185/210 · 88 % | −9 pp | pendiente | pendiente | — |
| Tipo | 30/30 · 100 % | 210/210 · 100 % | 0 pp | pendiente | pendiente | — |
| Prioridad | 27/30 · 90 % | 186/210 · 89 % | −1 pp | pendiente | pendiente | — |
| Pre-marcas · precisión | 12/18 · 67 % | 82/123 · 67 % | 0 pp | pendiente | pendiente | — |
| Pre-marcas · recall | 12/25 · 48 % | 82/175 · 47 % | −1 pp | pendiente | pendiente | — |
| Datos descartados antes del filtro | 0/116 · 0 % | 0/748 · 0 % | 0 pp | pendiente | pendiente | — |
| Respuestas rotas de la IA | — (sin IA) | — (sin IA) | — | pendiente | pendiente | — |
| Fallbacks a reglas | — (sin IA) | — (sin IA) | — | pendiente | pendiente | — |

## Degradación por tipo de ruido · Simulado

| Variante | Con ruido | Calle | Altura | Tipo | Prioridad | Pre-marcas P | Pre-marcas R |
|---|--:|--:|--:|--:|--:|--:|--:|
| original | — | 28/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| muletillas | 30/30 | 25/30 | 27/30 | 30/30 | 26/30 | 11/17 | 11/25 |
| numeros_en_palabras | 21/30 | 28/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| typos_asr | 30/30 | 28/30 | 29/30 | 30/30 | 25/30 | 11/16 | 11/25 |
| autocorreccion | 30/30 | 27/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| sin_av | 14/30 | 27/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| minusculas | 30/30 | 0/30 | 12/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| sin_direccion | 30/30 | 30/30 | 30/30 | 30/30 | 27/30 | 12/18 | 12/25 |

## Degradación por tipo de ruido · IA

**Pendiente.** Esta tabla se generó sin `LLM_API_KEY`, así que no hay corrida con IA y no se inventan sus números. Para completarla (el resultado se guarda en `data/eval/results/openai_compat.json` y esta tabla se regenera con las dos columnas):

```sh
cd backend && LLM_PROVIDER=openai_compat LLM_API_KEY=<clave> uv run python -m app.eval --provider openai_compat
```

`LLM_BASE_URL` y `LLM_MODEL` eligen el endpoint compatible con OpenAI (por defecto, Groq con `llama-3.3-70b-versatile`). `--concurrency` limita las llamadas simultáneas.

## Cómo se mide

- **Calle**: el nombre oficial al que llega el copiloto contra el nombre oficial de `calle_detectada` (los dos por el mismo matcher de calles).
- **Altura**: el número leído contra `altura_detectada` cuando es un número solo. Cuando trae una nota ("4500 (esquina)", "Km 7 (altura Parque Norte)", "S/N (…)") el relato no dice ningún número (EDA §7): el acierto es no leer altura.
- **Tipo** y **prioridad**: contra `categoria` y `prioridad_sugerida`.
- **Pre-marcas**: por cada mandatoria de la anotación manual que responde una señal del catálogo (`data/eval/mandatorias_senales.csv`), si el copiloto conoce esa señal contra si el relato la responde (A o P en la anotación). Las mandatorias que ninguna señal responde (antecedentes, tiempo de crisis, carriles…) no se pueden pre-marcar y quedan afuera. No mide si el valor (sí/no) es el correcto: la anotación no lo trae.
- **Datos descartados**: de los datos que propone el lector (ubicación, tipo, cada señal), los que se tiran por no tener evidencia en el relato o por estar fuera de las listas. En simulado es el lector por reglas; con IA, el lector con IA (la tasa de alucinación antes del filtro).
- **Respuestas rotas**: lecturas de la IA cuya respuesta no era válida tal como llegó (reparada, reintentada o abandonada). **Fallbacks**: lecturas que terminaron solo con reglas (respuesta inválida tras el reintento, timeout o error del proveedor).
- **Ruidoso**: las variantes juntas. En `sin_direccion` el gold de calle y altura es "ninguna": acierta si el copiloto no inventa una. El resto del gold es el del original.
- Una lectura por cada turno del llamante, sin acciones del operador.
