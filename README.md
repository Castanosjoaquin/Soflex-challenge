# Copiloto de Sala

Prototipo de un copiloto para el operador de atención de emergencias (líneas 911, 107, 103, 147 y
app). Lee la transcripción de la llamada turno por turno y, con la frase del relato que respalda cada
dato:

- sugiere la **ubicación** con nombres oficiales de calles, el **tipo** de incidente y la **prioridad**
  P1–P4 con su porqué;
- arma el **checklist de preguntas clave**, pre-marca lo que el relato ya respondió y propone la
  **próxima pregunta**;
- muestra las **instrucciones** de pre-arribo del protocolo y, ante una señal de P1, la **instrucción
  crítica** en el momento;
- arma la **Carta de Llamada** con lo que el operador confirmó y la deriva a una bandeja del
  despachador, donde después llegan las **ampliaciones**.

La IA solo propone datos con su cita. La prioridad, las preguntas, las instrucciones y la Carta salen
de reglas y de un catálogo escrito a mano, y nada se deriva sin que el operador lo confirme
([ADR 0001](docs/adr/0001-la-ia-solo-propone-senales-con-evidencia.md)). El copiloto no sugiere
recursos: eso lo decide el despachador.

Supuestos, trade-offs, resultados de la evaluación y limitaciones: **[DECISIONS.md](DECISIONS.md)**.

## Cómo correrlo

### Docker (modo simulado, sin credenciales)

```bash
docker compose up --build
```

El panel queda en <http://localhost:8000> y la bandeja del despachador en
<http://localhost:8000/despacho>. Sin `.env` arranca en **modo simulado** (`LLM_PROVIDER=mock`):
solo el Lector por reglas, sin red ni clave. El flujo completo funciona en este modo.

### Modo IA (opcional)

Suma el **Lector con IA** sobre cualquier endpoint compatible con OpenAI (Groq, Gemini, OpenAI,
Ollama…). Los dos lectores leen cada turno y se combinan (ver DECISIONS.md).

```bash
cp .env.example .env   # LLM_PROVIDER=openai_compat y LLM_API_KEY=<clave>
docker compose up --build
```

| Variable | Default | Para qué |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` o `openai_compat` |
| `LLM_API_KEY` | vacía | Sin clave, queda en modo simulado aunque diga `openai_compat` |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | Endpoint compatible con OpenAI (`.env.example` trae Groq, Gemini y Ollama) |
| `LLM_MODEL` | `qwen/qwen3.8-27b` | Modelo del endpoint |
| `LLM_TIMEOUT_SECONDS` | `8` | Tiempo máximo de la IA por lectura, reintento incluido; si se pasa, la lectura sigue solo con reglas |

El panel indica el modo de la llamada: *Modo simulado*, *IA* o *Modo reglas* (la IA falló y esa
lectura siguió solo con reglas).

Se probó contra Groq (`qwen/qwen3.8-27b`, ~1,5 s por lectura) y contra Gemini
(`gemini-3.5-flash-lite`, con el que está corrida la evaluación). Los planes gratuitos tienen límites
ajustados: Groq da 200.000 tokens por día y por modelo (unas 100 lecturas), y Gemini tuvo un 22 % de
timeouts y errores 503. En esos casos la lectura sigue solo con reglas, como está previsto.

### Desarrollo local

Requiere [uv](https://docs.astral.sh/uv/) y Node 22.

```bash
# Backend en :8000 (si existe frontend/dist, también sirve el panel)
cd backend && uv sync && uv run uvicorn app.main:app --reload

# Panel con hot reload en :5173 (hace proxy de /api a :8000)
cd frontend && npm install && npm run dev
```

Para el modo IA en local, pasá las variables en el entorno
(`LLM_PROVIDER=openai_compat LLM_API_KEY=… uv run uvicorn app.main:app`): el `.env` se lee desde el
directorio donde corre el backend, no desde la raíz.

Calidad:

```bash
cd backend && uv run pytest && uv run ruff check . && uv run mypy   # mypy strict
cd frontend && npm run build && npm run lint                         # tsc strict + oxlint
```

La API está documentada en <http://localhost:8000/docs> y en [SPEC §6](docs/SPEC.md#6-api).

## Cómo usarlo

Todo el flujo se hace con el teclado. `?` abre la ayuda con todos los atajos; la tabla de teclas vive
en un solo lugar, [`frontend/src/shortcuts.ts`](frontend/src/shortcuts.ts), y de ahí salen la ayuda y
cada pista en pantalla.

### Llamadas demo (empezar por acá)

Arriba de la lista están las seis llamadas demo: cada una extiende un caso del dataset a varios
turnos, con pausas, para que se vean las cinco etapas. Se abren con Tab + Enter (o un clic) y se
reproducen solas; `Espacio` pausa, `N` adelanta un turno y `X` va al doble de velocidad.

| Demo | Qué muestra |
|---|---|
| **DEMO-01** Pizzería en llamas (911) | El caso del video: AV. CORRIENTES 1540 casi Montevideo, incendio en comercio, P1 con su porqué e instrucción crítica «No vuelva a entrar al local». «Hay una garrafa» y «sale humo por la ventana del primer piso» pre-marcan gas y propagación. |
| **DEMO-02** Caída en la vereda (911) | Calle sin altura → «¿A qué altura de Corrientes?». Después el llamante cambia 1540 por 1450: sin confirmar gana el último valor; confirmado, aparece el aviso de contradicción. |
| **DEMO-03** Taxi contra moto (911) | Esquina San Juan y Entre Ríos, choque de moto P1 e instrucción crítica «No le saque el casco». |
| **DEMO-04** Árbol caído (103) | Av. Forest al 1200 entre dos calles; «no hay nadie atrapado» pre-marca un **no**. |
| **DEMO-05** Caño maestro (147) | Rotura de caño; «entra agua al subsuelo» sube la prioridad de P3 a P2. |
| **DEMO-06** Pelea en Plaza Serrano (911) | «Serrano» queda *a confirmar* (la calle está renombrada solo en parte); «sacó un cuchillo» y «no escuché disparos» pre-marcan sí y no. |

Recorrido corto con DEMO-01: cuando aparece la dirección, `C` la confirma y `T` confirma el tipo;
`L` marca leída la instrucción crítica; `D` deriva la Carta (en P1 el panel lo pide: «derivá ahora y
seguí preguntando»). Cuando llega «hay una garrafa», `V` confirma la pre-marca y la Carta suma una
**ampliación**, que se ve en `/despacho`. `R` abre el detalle técnico de cada lectura y `Q` cierra la
llamada.

Atajos más usados: `C` / `U` confirmar / corregir ubicación · `T` / `E` confirmar / elegir tipo ·
`F` / `G` tipo en disputa · `P` cambiar prioridad (pide motivo) · `1` `2` `3` Sí / No / No sabe ·
`S` saltear · `V` confirmar pre-marca · `L` instrucción leída · `A` / `M` aviso: tomar / mantener ·
`D` derivar · `O` nota del operador. La lista completa está en `?`.

### Otras fuentes

- **Dataset**: las 30 llamadas sintéticas provistas, de un intercambio cada una.
- **Pegar un relato**: texto propio, con prefijos `Operador:` / `Llamante:` para separar turnos (sin
  prefijos es un solo turno del llamante) y la línea por la que entra.

## Evaluación

```bash
cd backend && uv run python -m app.eval --provider mock
```

Corre las 30 llamadas del dataset y 210 variantes ruidosas (7 tipos de ruido, semilla fija,
versionadas en `data/eval/noisy/` y regenerables con `uv run python -m app.eval.noise`) y reescribe
[`data/eval/resultados.md`](data/eval/resultados.md). Mide calle, altura, tipo, prioridad, precisión
y recall de las pre-marcas, datos descartados por falta de evidencia y, con IA, respuestas rotas y
fallbacks. No es parte de pytest y tarda menos de un segundo en modo simulado.

Con IA (240 lecturas; `--pause` las espacia para no pasar el límite por minuto de un plan gratuito):

```bash
cd backend && LLM_PROVIDER=openai_compat LLM_API_KEY=<clave> uv run python -m app.eval --provider openai_compat --concurrency 1 --pause 4
```

La corrida publicada es con Gemini (`LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`,
`LLM_MODEL=gemini-3.5-flash-lite`), porque la cuota diaria gratuita de Groq no alcanza para las 240
lecturas.

Con n = 30 los números no permiten afirmar nada estadísticamente. La tabla y sus advertencias están en
[DECISIONS.md](DECISIONS.md#evaluación).

## Estructura

```
backend/app/
  catalog/      dataset, señales, tipos y subtipos, prioridad, preguntas, instrucciones, calles, demos
  transcript/   parser de turnos y normalizador con mapa de offsets
  readers/      lector por reglas (rules/) y lector con IA (ia/), con la misma salida
  engine/       verificación, combinación, prioridad, checklist, contradicciones, Carta
  calls/        llamada en memoria, acciones del operador, registro de acciones (SQLite)
  dispatch/     bandeja del despachador: Cartas y ampliaciones (SQLite)
  trace/        traza de cada lectura y métricas
  eval/         evaluación (python -m app.eval) y generador de ruido
backend/tests/  pytest (unitarios, integridad del catálogo, API de punta a punta en modo mock)
frontend/src/   panel del operador y /despacho (React + TypeScript + Vite)
data/           dataset provisto, llamadas demo, lista de calles y evaluación
scripts/        build_streets.py: regenera data/streets.json desde BA Data
docs/           SPEC, DESIGN, ADR, EDA del dataset y estado del arte
```

Documentación: [DECISIONS.md](DECISIONS.md) (supuestos, trade-offs, evaluación, limitaciones) ·
[docs/SPEC.md](docs/SPEC.md) (qué se construyó) · [docs/DESIGN.md](docs/DESIGN.md) (por qué) ·
[CONTEXT.md](CONTEXT.md) (vocabulario) · [docs/adr/](docs/adr/) ·
[docs/research/eda/EDA.md](docs/research/eda/EDA.md) · [docs/research/sota/SOTA.md](docs/research/sota/SOTA.md).

## Datos y atribución

- `data/dataset_challenge_soflex.csv`: el dataset sintético provisto con el challenge.
- `data/streets.json`, la lista oficial de calles de CABA (nombre oficial, nombres anteriores y rango
  de alturas), se genera a partir del dataset **«Calles»** de
  [BA Data](https://data.buenosaires.gob.ar/dataset/calles), del Gobierno de la Ciudad Autónoma de
  Buenos Aires, publicado bajo licencia **Creative Commons Atribución (CC-BY)**. Archivo de origen:
  `https://cdn.buenosaires.gob.ar/datosabiertos/datasets/jefatura-de-gabinete-de-ministros/calles/callejero.csv`.
  Se usa transformado: de los 31.961 tramos del callejero se guarda un registro por nombre oficial
  (2.675).

`streets.json` está commiteado: ni la app ni el build de Docker acceden a internet. Para regenerarlo:

```bash
cd backend && uv run python ../scripts/build_streets.py
```
