# Spec — Copiloto de Sala (MVP)

> Fuente: [DESIGN.md](DESIGN.md) (el porqué) · vocabulario en [CONTEXT.md](../CONTEXT.md) ·
> decisión central en [ADR 0001](adr/0001-la-ia-solo-propone-senales-con-evidencia.md).
> Este documento dice **qué** se construye y **cómo se sabe que está hecho**. Si contradice al diseño,
> manda este documento y el diseño se corrige.

## 1. Objetivo

Un panel web en `http://localhost:8000`, levantado con `docker compose up --build`, en el que un
operador reproduce una llamada turno por turno y el copiloto:

1. Sugiere la **ubicación** (calles con nombre oficial), el **tipo/subtipo** de incidente y la
   **prioridad** P1–P4 con su porqué, siempre con **evidencia**.
2. Muestra el **checklist de preguntas clave** pre-marcado y la **próxima pregunta**.
3. Muestra las **instrucciones** del protocolo (y la **instrucción crítica** en el momento).
4. Permite al operador **confirmar, corregir y derivar** la **Carta de Llamada** con el teclado, y
   seguir mandando **ampliaciones**.

Todo funciona sin credenciales (`LLM_PROVIDER=mock`). Con una clave de un endpoint compatible con
OpenAI se suma el **Lector con IA**.

## 2. Fuera de alcance

Audio y ASR · callejero con alturas y geometría (validación de esquina, barrio, comuna, mapa) ·
geocoders online · lectura progresiva · tablero de métricas · login y varios operadores ·
la IA redactando la Carta · recursos sugeridos · "casos similares" y few-shot.

## 3. Arquitectura

Un solo contenedor: FastAPI (Python 3.12, Pydantic v2, mypy strict) que sirve la API en `/api` y el
panel (React + Vite + TS) ya compilado.

```
backend/app/
  catalog/      dataset (existe) + protocolo curado + calles oficiales
  transcript/   parser de turnos y normalizador con offsets
  readers/      lector por reglas, lector con IA, proveedores
  engine/       verificación, combinación, confianza, prioridad, checklist, etapas, instrucciones, Carta
  calls/        llamada en memoria, acciones del operador, registro de acciones (SQLite)
  dispatch/     bandeja del despachador (Cartas + ampliaciones, SQLite)
  traces/       trazas de lectura y métricas
  eval/         runner de evaluación (python -m app.eval)
  api.py
```

**Regla de dependencias:** `engine` no conoce HTTP ni al proveedor de IA. Recibe lecturas
(`ReaderOutput`) y el estado de la llamada, y devuelve el estado nuevo. Los dos lectores devuelven el
mismo tipo `ReaderOutput`.

## 4. Modelo

Todos los modelos son Pydantic y viven del lado del backend. El frontend replica en TS solo lo que
consume (`CallState` y lo que cuelga de ella).

- **Turno** `{index, speaker: operador|llamante, text, at_ms}`
- **Evidencia** `{turn_index, start, end, quote}`: offsets sobre el texto **original** del turno.
- **Señal** (catálogo): `{id, label, question_hint}`. Ejemplos: `persona_atrapada`, `respira`,
  `consciente`, `fuego_activo`, `humo`, `gas`, `riesgo_electrico`, `arma_fuego`, `arma_blanca`,
  `sangrado_abundante`, `heridos`, `menores`, `evacuado`, `propagacion`, `derrame_combustible`,
  `atrapado_vehiculo`, `motociclista`, `agua_sube`, `estructura_cede`, `cables_caidos`,
  `involucrados_en_lugar`, `animal_mordedura`, `explosion`, `dificultad_respirar`, `golpe_cabeza`.
  Son unas 25; la lista final la cierra el ticket del catálogo.
- **SignalValue** `{signal_id, value: si|no|no_sabe, evidence?, source: reglas|ia|operador, confidence}`
- **Ubicación** `{said: str, evidence[], street_official?, number?: {value?, kind: exacta|al|esquina|km|sn}, cross_streets[], candidates[], confidence}`
- **Tipo** = `Category` (los 6 que existen); **Subtipo** = enum del catálogo, por tipo.
- **Prioridad** `{level: P1..P4, reasons: [{signal_id, evidence}], overridden_by_operator?: {from, reason}}`
- **PreguntaClave** (catálogo): `{id, type, subtypes?, text, signal_id, order}`
- **Instrucción** (catálogo): `{id, text, critical: bool, applies_when: condición sobre tipo/subtipo/señales, order}`
- **CallState**: línea, turnos, ubicación, tipo (o par en disputa), señales, prioridad, checklist con
  estados, próxima pregunta, instrucciones (con leída sí/no), instrucción crítica activa, etapas,
  avisos de contradicción, modo (`ia`|`reglas`|`simulado`), Carta en vivo, derivada sí/no,
  ampliaciones.

Confianza: `confirmado` (lo validó el operador) · `probable` (evidencia verificada y sin
contradicción) · `a_confirmar` (sin evidencia suficiente, lectores en desacuerdo o contradicción).

## 5. Comportamiento

### 5.1 Ingreso del relato
- Parser: separa `Operador:` / `Llamante:`. Un texto sin prefijos es un solo turno del llamante.
- Fuentes: las 30 llamadas del dataset (2 turnos cada una), 5–6 llamadas de demo extendidas
  (`data/demo_calls/*.json`, con `delay_ms` por turno) y texto pegado.
- La **reproducción en vivo** la hace el frontend: manda un `POST` por turno respetando las pausas, y
  tiene botones de pausa, siguiente turno y velocidad ×2.

### 5.2 Normalización (antes de leer)
Saca muletillas, pasa números en palabras a dígitos ("mil quinientos cuarenta" → 1540), unifica
abreviaturas (`Av.`, `Gral.`) y aplica la autocorrección dentro de un turno ("…no, perdón, en X" → X).
Mantiene un **mapa de offsets** de normalizado a original para poder resaltar la evidencia.

### 5.3 Lectura
- Cada turno nuevo dispara una lectura completa del relato. Las lecturas se **serializan** por
  llamada: si llega un turno con una lectura en curso, se encola.
- **Lector por reglas** (siempre): patrones de ubicación por capas (EDA, implicancia 1), keywords con
  peso para las señales, keywords más la línea como prior para el tipo y el subtipo, y patrones de
  respuesta por pregunta clave.
- **Lector con IA** (si `effective_provider == openai_compat`):
  - El prompt incluye el relato delimitado y marcado como datos del llamante, la lista cerrada de
    señales, tipos y subtipos, las preguntas clave del tipo, y tres reglas: solo lo que está en la
    lista, cita textual obligatoria y "no se sabe" si no se dijo.
  - Pide `response_format: json_object` y valida con Pydantic. Si falla, primero intenta una
    reparación local (extraer el JSON y recortar). Si sigue fallando, hace **un** reintento con el
    error de validación. Si vuelve a fallar, sigue solo con reglas y pasa a modo `reglas`.
  - Timeout de **8 s** (configurable). Si vence, también pasa a modo `reglas`.

### 5.4 Verificación y combinación
1. Cada evidencia se busca en el relato (match exacto normalizado y, si no, fuzzy ≥ 0,9 dentro de un
   turno del llamante). Si no se encuentra, **se descarta** el dato y se registra en la traza.
2. Coherencia: los pares contradictorios (`respira=no` con "está hablando", etc.) pasan a
   `a_confirmar`.
3. Las señales de los dos lectores se **unen**. Si discrepan en el valor de una misma señal, queda
   `a_confirmar` con las dos evidencias.
4. Si discrepan en el tipo, la llamada queda en **tipo en disputa** y el operador elige con una tecla.
   Mientras tanto la prioridad se calcula para los dos tipos y gana la **más alta**.
5. **Nunca se pisa lo confirmado.** Si un dato no confirmado cambia, gana el último valor
   (autocorrección). Si cambia un dato confirmado, el dato queda como está y se genera un **aviso de
   contradicción** ("Antes dijo X, ahora dice Y") que el operador acepta o descarta.

### 5.5 Ubicación (etapa ①)
- Lista oficial de calles de CABA: la genera un script desde BA Data "Calles" (CC-BY) y se commitea
  como `data/streets.json` (nombre oficial + nombres anteriores y alias). Funciona sin internet.
- Matching: exacto → alias → fuzzy (rapidfuzz o difflib) + fonético español (simplificaciones b/v,
  ll/y, s/z/c, h muda). Si no hay match, queda como se dijo, en `a_confirmar`.
- Pregunta de ubicación faltante, según DESIGN §Paso 4 (sin altura, solo lugar, avenida o calle, nada).
- Se completa cuando el operador confirma (o corrige) la dirección.

### 5.6 ¿Qué pasa? (etapa ②)
- Tipo y subtipo sugeridos. Si hay víctimas sin `consciente`/`respira` conocidos, la próxima pregunta
  es la universal.
- Prioridad por **tabla de reglas** (DESIGN §Paso 5), con P4 solo si no hay ninguna señal de P1–P3 y
  el incidente es un reclamo. Siempre con su porqué.
- El operador puede cambiar la prioridad; tiene que dar un motivo, que se registra.
- Se completa cuando el tipo está confirmado y el riesgo vital está evaluado (o no hay víctimas).

### 5.7 Preguntas clave (etapa ③)
- El checklist se arma con el catálogo según tipo y subtipo, ordenado por criticidad. Cada pregunta
  está atada a una señal.
- Estados por pregunta: `pendiente` · `pre_marcada(valor, evidencia)` · `respondida(valor, por operador)` · `salteada`.
- **Próxima pregunta** = la primera pregunta faltante de la etapa más temprana sin completar: primero
  ubicación, después la universal y después las preguntas clave.
- Teclas: confirmar pre-marca · Sí / No / No sabe · saltear.

### 5.8 Instrucciones (etapa ⑤) e instrucción crítica
- Se filtran del catálogo por `applies_when` y se ordenan con la prohibición más importante primero.
- **Instrucción crítica**: cuando aparece una señal de P1, se muestra arriba de todo, en rojo, sin
  importar la etapa. Solo hay una activa a la vez.
- El operador marca cada una como leída, y esa acción queda en el registro.

### 5.9 Derivar (etapa ④), bandeja y ampliaciones
- **Derivar** se habilita con la ubicación y el tipo confirmados. En P1 aparece "P1 · derivá ahora y
  seguí preguntando".
- La Carta se arma con una **plantilla** (no con IA) y solo con datos confirmados. Lleva dónde (dicho
  y normalizado), qué pasa (tipo, subtipo y resumen de señales), prioridad y porqué, quién está en
  riesgo, instrucciones dadas, preguntas que faltan, y el origen de cada dato. **No lleva recursos.**
- Al derivar, la Carta se guarda en SQLite y aparece en la **bandeja del despachador** (`/despacho`,
  con polling cada 2 s).
- Después de derivar, cada dato que el operador confirma (respuesta, cambio de prioridad, ubicación
  corregida) genera una **ampliación** que también va a la bandeja.
- Cerrar la llamada la marca como terminada. El estado en memoria se descarta; el registro queda.

### 5.10 Registro de acciones
Tabla SQLite append-only (sin UPDATE ni DELETE en el repositorio): `call_id, at, action, target,
before, after, reason`. Registra cada confirmación, corrección, respuesta, cambio de prioridad,
instrucción leída, derivación, ampliación, nota y cierre.

### 5.11 Detalle técnico y métricas
- Por cada lectura se guarda una **traza**: duración por paso, señales encontradas por cada lector,
  intentos de la IA (con el error si hubo), datos descartados con su motivo, desacuerdos y cambios
  aplicados. Se ve en un panel oculto por defecto, con el formato de DESIGN §9.
- `GET /api/metrics`: latencias, respuestas rotas de la IA, fallbacks, descartes por falta de
  evidencia, desacuerdos, pre-marcas confirmadas vs. corregidas por pregunta y tiempo hasta derivar.

## 6. API

| Método y ruta | Qué hace |
|---|---|
| `GET /api/health` | Estado, proveedor efectivo y tamaño del catálogo (existe) |
| `GET /api/samples` · `GET /api/samples/{id}` | Llamadas de prueba del dataset más las demo, con sus turnos |
| `POST /api/calls` `{line, sample_id?}` | Abre una llamada → `CallState` |
| `POST /api/calls/{id}/turns` `{speaker, text}` | Agrega un turno, lee y devuelve → `CallState` |
| `POST /api/calls/{id}/actions` `{kind, target?, value?, reason?}` | Acción del operador → `CallState` |
| `POST /api/calls/{id}/derive` | Deriva → `CallState` |
| `POST /api/calls/{id}/close` | Cierra la llamada |
| `GET /api/calls/{id}/readings` | Trazas de las lecturas |
| `GET /api/dispatch` | Cartas derivadas con sus ampliaciones |
| `GET /api/metrics` | Números generales |

Valores de `kind`: `confirm_location`, `correct_location`, `confirm_type`, `choose_type`,
`confirm_premark`, `answer_question`, `skip_question`, `set_priority`, `mark_instruction_read`,
`resolve_contradiction`, `add_note`.

## 7. Panel

Layout según DESIGN §8: barra de etapas con la próxima pregunta e instrucción crítica arriba; a la
izquierda el relato con la evidencia resaltada (al pasar por un dato se ilumina su frase); en el
centro ubicación, qué pasa con la prioridad y el checklist; a la derecha las instrucciones; abajo la
Carta en vivo, el botón Derivar y las ampliaciones; el detalle técnico se despliega aparte. Un
indicador muestra el modo (simulado / IA / reglas por fallback). La bandeja del despachador está en
`/despacho`.

**Teclado:** todas las acciones de §6 tienen atajo. Hay una ayuda visible (`?`). La única caja de
texto libre es la de la nota del operador.

## 8. Evaluación

`uv run python -m app.eval [--provider mock|openai_compat]`:
- Corpus: las 30 llamadas del dataset, las demo extendidas y variantes ruidosas generadas por
  `app.eval.noise` con semilla fija y versionadas en `data/eval/noisy/` (muletillas, números en
  palabras, typos de ASR, autocorrección, sin "Av.", sin dirección).
- Gold: columnas del CSV para categoría, prioridad, calle y altura; la anotación manual de las 90
  preguntas mandatorias (`data/eval/mandatorias_anotacion_manual.csv`) para el checklist.
- Métricas: exact-match de calle normalizada, altura, tipo y prioridad; precisión y recall de las
  pre-marcas; datos descartados por falta de evidencia (tasa de alucinación antes del filtro);
  respuestas rotas y fallbacks; degradación de original a ruidoso. Las calcula para los dos modos.
- Salida: una tabla Markdown que se pega en `DECISIONS.md`, avisando que con n=30 no se puede afirmar
  nada estadísticamente.

## 9. Calidad y DX

- `uv run pytest`, `ruff check` y `mypy` (strict) en verde. El frontend usa `tsc` strict y oxlint.
- Tests: unitarios del normalizador, el lector de ubicación, el matcher de calles, la tabla de
  prioridad, la verificación y la combinación; un test de integridad del catálogo (toda pregunta
  apunta a una señal que existe, toda instrucción tiene una condición válida); tests de API de punta a
  punta en modo mock (abrir → turnos → confirmar → derivar → ampliación). El lector con IA se testea
  con un cliente HTTP falso que devuelve JSON roto, incompleto, con citas inventadas y timeouts.
- No hay secretos en el repo. `docker compose up --build` funciona sin `.env`.
- Commits chicos y con mensaje convencional, uno o más por ticket.

## 10. Criterios de aceptación del MVP

1. `docker compose up --build` en una máquina limpia → el panel en `:8000` en modo simulado.
2. Reproducir la llamada de la pizzería (demo extendida): aparece la ubicación `AV. CORRIENTES 1540`
   casi `MONTEVIDEO`, el tipo incendio en comercio, P1 con su porqué y la instrucción crítica "No
   vuelva a entrar…", todo con su evidencia resaltada.
3. Con dos teclas de confirmación más Derivar, la Carta aparece en `/despacho`. El turno "hay una
   garrafa" pre-marca la pregunta de gas; al confirmarla, llega una ampliación.
4. Una demo con dirección incompleta muestra la pregunta de ubicación; un cambio de altura después de
   confirmar muestra el aviso de contradicción y no pisa el dato.
5. Con IA configurada: el detalle técnico muestra al menos un dato descartado por falta de evidencia
   y, forzando JSON roto en los tests, el reintento y el fallback a reglas.
6. Las 30 llamadas del dataset se pueden cargar y ninguna rompe el flujo.
7. `README.md` y `DECISIONS.md` (supuestos, trade-offs, tabla de evaluación, "con más tiempo").
