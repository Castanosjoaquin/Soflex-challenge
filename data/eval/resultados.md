# Evaluación del copiloto

> **Con n = 30 no se puede afirmar nada estadísticamente.** Un caso mueve 3,3 puntos y ninguna diferencia de estas tablas es significativa: sirven para ver dónde falla el copiloto, no para decir que un modo es mejor que otro. Además, las reglas y el catálogo se escribieron mirando estos mismos 30 casos (EDA §8): los números del original son optimistas, y las variantes ruidosas son la medida más honesta.

Corpus: las 30 llamadas del dataset tal como vienen (*original*) y 7 variantes ruidosas de cada una (*ruidoso*, 210 llamadas, semilla 13, en `data/eval/noisy/`). Se genera con `uv run python -m app.eval.noise` y se corre con `uv run python -m app.eval [--provider mock|openai_compat]` desde `backend/`.

## Resultados

| Métrica | Simulado · original | Simulado · ruidoso | Δ | IA · original | IA · ruidoso | Δ |
|---|--:|--:|--:|--:|--:|--:|
| Calle (nombre oficial) | 28/30 · 93 % | 197/210 · 94 % | 0 pp | 28/30 · 93 % | 193/210 · 92 % | −1 pp |
| Altura | 29/30 · 97 % | 204/210 · 97 % | 0 pp | 29/30 · 97 % | 204/210 · 97 % | 0 pp |
| Tipo | 30/30 · 100 % | 210/210 · 100 % | 0 pp | 30/30 · 100 % | 210/210 · 100 % | 0 pp |
| Prioridad | 27/30 · 90 % | 188/210 · 90 % | 0 pp | 26/30 · 87 % | 173/210 · 82 % | −4 pp |
| Pre-marcas · precisión | 12/18 · 67 % | 84/126 · 67 % | 0 pp | 14/22 · 64 % | 95/140 · 68 % | +4 pp |
| Pre-marcas · recall | 12/25 · 48 % | 84/175 · 48 % | 0 pp | 14/25 · 56 % | 95/175 · 54 % | −2 pp |
| Datos descartados antes del filtro | 0/116 · 0 % | 0/782 · 0 % | 0 pp | 2/99 · 2 % | 9/647 · 1 % | −1 pp |
| Respuestas rotas de la IA | — (sin IA) | — (sin IA) | — | 0/30 · 0 % | 0/210 · 0 % | 0 pp |
| Fallbacks a reglas | — (sin IA) | — (sin IA) | — | 6/30 · 20 % | 46/210 · 22 % | +2 pp |

## Degradación por tipo de ruido · Simulado

| Variante | Con ruido | Calle | Altura | Tipo | Prioridad | Pre-marcas P | Pre-marcas R |
|---|--:|--:|--:|--:|--:|--:|--:|
| original | — | 28/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| muletillas | 30/30 | 28/30 | 29/30 | 30/30 | 26/30 | 12/18 | 12/25 |
| numeros_en_palabras | 21/30 | 28/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| typos_asr | 30/30 | 28/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| autocorreccion | 30/30 | 28/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| sin_av | 14/30 | 27/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| minusculas | 30/30 | 28/30 | 29/30 | 30/30 | 27/30 | 12/18 | 12/25 |
| sin_direccion | 30/30 | 30/30 | 30/30 | 30/30 | 27/30 | 12/18 | 12/25 |

## Degradación por tipo de ruido · IA

Modelo: `gemini-3.5-flash-lite`.

**Ojo:** 52 de 240 lecturas cayeron a reglas (timeout, error del proveedor o respuesta inválida): en esas llamadas los números son los de las reglas.

| Variante | Con ruido | Calle | Altura | Tipo | Prioridad | Pre-marcas P | Pre-marcas R |
|---|--:|--:|--:|--:|--:|--:|--:|
| original | — | 28/30 | 29/30 | 30/30 | 26/30 | 14/22 | 14/25 |
| muletillas | 30/30 | 28/30 | 29/30 | 30/30 | 25/30 | 14/20 | 14/25 |
| numeros_en_palabras | 21/30 | 28/30 | 29/30 | 30/30 | 26/30 | 13/20 | 13/25 |
| typos_asr | 30/30 | 28/30 | 29/30 | 30/30 | 24/30 | 15/21 | 15/25 |
| autocorreccion | 30/30 | 28/30 | 29/30 | 30/30 | 25/30 | 13/19 | 13/25 |
| sin_av | 14/30 | 27/30 | 29/30 | 30/30 | 26/30 | 14/20 | 14/25 |
| minusculas | 30/30 | 28/30 | 29/30 | 30/30 | 24/30 | 12/20 | 12/25 |
| sin_direccion | 30/30 | 26/30 | 30/30 | 30/30 | 23/30 | 14/20 | 14/25 |

## Cómo se mide

- **Calle**: el nombre oficial al que llega el copiloto contra el nombre oficial de `calle_detectada` (los dos por el mismo matcher de calles).
- **Altura**: el número leído contra `altura_detectada` cuando es un número solo. Cuando trae una nota ("4500 (esquina)", "Km 7 (altura Parque Norte)", "S/N (…)") el relato no dice ningún número (EDA §7): el acierto es no leer altura.
- **Tipo** y **prioridad**: contra `categoria` y `prioridad_sugerida`.
- **Pre-marcas**: por cada mandatoria de la anotación manual que responde una señal del catálogo (`data/eval/mandatorias_senales.csv`), si el copiloto conoce esa señal contra si el relato la responde (A o P en la anotación). Las mandatorias que ninguna señal responde (antecedentes, tiempo de crisis, carriles…) no se pueden pre-marcar y quedan afuera. No mide si el valor (sí/no) es el correcto: la anotación no lo trae.
- **Datos descartados**: de los datos que propone el lector (ubicación, tipo, cada señal), los que se tiran por no tener evidencia en el relato o por estar fuera de las listas. En simulado es el lector por reglas; con IA, el lector con IA (la tasa de alucinación antes del filtro).
- **Respuestas rotas**: lecturas de la IA cuya respuesta no era válida tal como llegó (reparada, reintentada o abandonada). **Fallbacks**: lecturas que terminaron solo con reglas (respuesta inválida tras el reintento, timeout o error del proveedor).
- **Ruidoso**: las variantes juntas. En `sin_direccion` el gold de calle y altura es "ninguna": acierta si el copiloto no inventa una. El resto del gold es el del original.
- Una lectura por cada turno del llamante, sin acciones del operador.
