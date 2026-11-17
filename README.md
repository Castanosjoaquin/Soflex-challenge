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
data/      Dataset sintético provisto
docs/      Configuración para agentes y ADRs
```
