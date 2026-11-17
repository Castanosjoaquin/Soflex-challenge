# Copiloto de Sala

Asistente para operadores de atención de emergencias (911 / 147): procesa la transcripción de una
llamada, extrae ubicación, tipología y prioridad, muestra instrucciones de pre-arribo y el checklist
de protocolo, y permite derivar la Carta de Llamada al despacho.

> 🚧 En construcción. Las decisiones de diseño se documentarán en `DECISIONS.md`.

## Levantar el proyecto

```bash
docker compose up --build
```

Panel en <http://localhost:8000>. Por defecto corre en **modo simulado** (`LLM_PROVIDER=mock`):
no requiere credenciales ni conexión.

### Modo LLM real (opcional)

```bash
cp .env.example .env   # completar LLM_PROVIDER=openai_compat y LLM_API_KEY
docker compose up --build
```

Funciona con cualquier endpoint compatible con OpenAI (Groq, Gemini, OpenAI, Ollama).

Cada turno lo leen los dos lectores, el de reglas y el de IA, y se combinan: las señales se unen, los
valores en desacuerdo quedan "a confirmar" con las dos frases y, si los tipos difieren, el operador
elige con una tecla (`A` / `B`). La IA solo propone ubicación, tipo y señales, cada uno con su frase,
que se verifica contra el relato; la prioridad, las preguntas y las instrucciones salen siempre de las
reglas. Si la IA no responde en `LLM_TIMEOUT_SECONDS` (8 s) o responde mal dos veces, la lectura sigue
solo con reglas y el panel muestra "Modo reglas". Sin `LLM_API_KEY`, todo queda en modo simulado.

## Desarrollo local

```bash
# Backend (requiere uv)
cd backend && uv sync && uv run uvicorn app.main:app --reload

# Panel con hot reload (proxy de /api → :8000)
cd frontend && npm install && npm run dev

# Calidad
cd backend && uv run pytest && uv run ruff check . && uv run mypy
```

## Estructura

```
backend/   FastAPI + Pydantic: API, catálogo de referencia, extracción
frontend/  Panel del operador (React + TypeScript + Vite)
data/      Dataset sintético provisto y lista oficial de calles (streets.json)
scripts/   build_streets.py: regenera data/streets.json desde BA Data
docs/      Configuración para agentes y ADRs
```

## Datos de terceros

`data/streets.json` (la lista oficial de calles de CABA, con nombres anteriores y rango de alturas)
se genera a partir del dataset **"Calles"** de [BA Data](https://data.buenosaires.gob.ar/dataset/calles),
del Gobierno de la Ciudad Autónoma de Buenos Aires, publicado bajo licencia **Creative Commons
Atribución (CC-BY)**. Se usa transformado: de los ~32.000 tramos del callejero solo se guarda un
registro por nombre oficial.

El archivo está commiteado: ni la app ni `docker compose up --build` acceden a internet para usarlo.
Para regenerarlo:

```bash
cd backend && uv run python ../scripts/build_streets.py
```
