# Copiloto de Sala

Asistencia en pantalla al operador de atención de emergencias (911 / 147) mientras atiende una
llamada: entiende el relato, sugiere y arma la Carta de Llamada que se deriva al despacho.

## Personas

**Operador**:
Quien atiende la llamada, contiene al llamante, conduce el interrogatorio y decide. Es el único que confirma datos y deriva.
_Avoid_: usuario, agente

**Llamante**:
El ciudadano que llama y relata la emergencia.
_Avoid_: ciudadano, denunciante, caller

**Despachador**:
Quien recibe la Carta en el CAD y asigna recursos en la calle. El copiloto no decide recursos.
_Avoid_: dispatcher, CAD (el CAD es el sistema, no la persona)

## La llamada

**Llamada**:
Una conversación entre operador y llamante, desde que se abre hasta que el operador la cierra. Entra por una **Línea** (911, 107, 103, 147 o app).
_Avoid_: caso, sesión, registro

**Turno**:
Lo que dice una sola de las partes (operador o llamante) antes de que hable la otra.
_Avoid_: mensaje, frase, línea

**Relato**:
La secuencia completa de turnos de una llamada hasta el momento actual.
_Avoid_: transcripción (es el insumo técnico, no el concepto), texto

**Etapa**:
Uno de los cinco momentos del protocolo: Ubicar, ¿Qué pasa?, Preguntas clave, Derivar, Instrucciones. Cada una está hecha, actual o pendiente; no se recorren en orden obligatorio.
_Avoid_: paso, fase

## Lo que se entiende del relato

**Lectura**:
Una pasada de los lectores sobre el relato completo, disparada por cada turno nuevo.
_Avoid_: extracción, análisis, inferencia

**Lector**:
Quien hace una lectura: el **Lector por reglas** (siempre) o el **Lector con IA** (opcional). Solo proponen; nunca deciden.
_Avoid_: extractor, modelo, provider

**Señal**:
Un dato atómico del catálogo cerrado (~25) que el relato puede afirmar o negar, como *persona atrapada*, *respira* o *hay gas*. Vale sí, no o no se sabe.
_Avoid_: hecho, feature, flag, riesgo

**Evidencia**:
La frase textual del relato que respalda una señal o un dato de ubicación. Sin evidencia encontrada en el relato, el dato se descarta.
_Avoid_: cita, fuente, span

**Traza**:
El detalle técnico de una lectura, paso por paso: cuánto tardó cada paso, qué leyó cada lector, qué se descartó y por qué, en qué no coincidieron y qué cambió. Es para el equipo técnico, no para el operador.
_Avoid_: log, debug

**Confianza**:
El estado de cada dato sugerido: **confirmado** (lo validó el operador), **probable** (tiene evidencia verificada y nada lo contradice) o **a confirmar** (sin respaldo suficiente, lectores en desacuerdo o contradicción). Nunca es un porcentaje.
_Avoid_: score, certeza, probabilidad

**Autocorrección**:
Cuando el llamante cambia un dato que el operador todavía no confirmó. Gana el último valor, sin aviso.

**Contradicción**:
Cuando el relato cambia un dato que el operador ya confirmó. El dato confirmado no se toca y se muestra un aviso.
_Avoid_: conflicto, inconsistencia

## El incidente

**Incidente**:
Lo que está pasando, según lo entiende la sala. Tiene un **Tipo** (lista fija de seis) y un **Subtipo** que cambia las instrucciones.
_Avoid_: hecho, evento, caso, categoría

**Ubicación**:
Dónde es el incidente: lo que **dijo** el llamante y la **dirección** normalizada a nombres oficiales de calles.
_Avoid_: dirección (cuando se habla del concepto completo), lugar

**Prioridad**:
Nivel de urgencia P1 a P4, calculado por reglas a partir de las señales y siempre acompañado de su **porqué** (las señales y evidencias que la dispararon).
_Avoid_: severidad, nivel de riesgo, triage

## El protocolo

**Pregunta clave**:
Una pregunta del checklist del protocolo para un tipo de incidente. Está atada a una señal y se responde cuando esa señal se conoce.
_Avoid_: pregunta mandatoria, ítem

**Pre-marca**:
Respuesta a una pregunta clave que el copiloto propone desde el relato, con su evidencia, y que espera la confirmación del operador.
_Avoid_: autocompletado, sugerencia de respuesta

**Próxima pregunta**:
La pregunta clave (o de ubicación) más importante que sigue sin respuesta. Es la única que se muestra en grande.

**Instrucción**:
Indicación de seguridad o de pre-arribo, escrita de antemano en el protocolo, para que el operador la lea en voz alta. La IA nunca la redacta.
_Avoid_: consejo, recomendación

**Instrucción crítica**:
La instrucción más importante ante una señal de P1. Se muestra en el momento, sin esperar a su etapa.

## La derivación

**Carta de Llamada**:
El resumen estructurado del incidente que el operador deriva al despachador. Lleva cada dato con su origen (dicho, normalizado o cargado por el operador) y lo que falta preguntar. No lleva recursos.
_Avoid_: ficha, ticket, reporte

**Derivar**:
El acto del operador que manda la Carta al despachador. Se habilita con ubicación y tipo confirmados.
_Avoid_: despachar (eso lo hace el despachador), enviar

**Ampliación**:
Un dato confirmado después de derivar, que se agrega a la Carta ya derivada.
_Avoid_: actualización, addendum

**Nota del operador**:
Lo único que el operador escribe con sus palabras: algo que el relato no dice. Va a la Carta tal cual; después de derivar, como ampliación.
_Avoid_: comentario, observación

**Registro de acciones**:
La lista, que no se puede borrar, de todo lo que hizo el operador en una llamada.
_Avoid_: log, historial, audit trail
