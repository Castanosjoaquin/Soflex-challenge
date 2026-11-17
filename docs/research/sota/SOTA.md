# Estado del arte: copilotos para la toma de llamadas de emergencia (911/147)

> Investigación para el challenge "Operator Copilot" de Soflex. Fecha de corte: noviembre 2026.
> Convención: **[vendor]** = afirmación de marketing o caso publicado por el propio proveedor, sin verificación independiente. **[peer-reviewed]** = estudio revisado por pares. **[preprint]** = arXiv/actas sin revisión formal completa. **[prensa]** = periodismo o prensa sectorial.

---

## Resumen ejecutivo

- **El mercado convergió en un mismo patrón: "asistir, no decidir".** Prepared/Axon 911, Carbyne, RapidSOS HARMONY, Motorola Assist, Aurelian Cora y Hexagon Smart Advisor ofrecen transcripción en vivo, traducción, resaltado de keywords (ubicación, nombres, naturaleza del incidente), resúmenes para el CAD y, cada vez más, sugerencia de las preguntas del protocolo. Todos insisten en que el humano mantiene el control. Casi ninguna cifra de impacto está verificada de forma independiente.
- **La mejor evidencia científica viene de Copenhague (Corti).** El modelo detecta paro cardíaco (OHCA) con mayor sensibilidad que los operadores (85% vs 77,5%), pero en el ensayo randomizado **no mejoró** el reconocimiento por parte de los humanos (93,1% vs 90,5%, p=0,15). La causa: un PPV de alerta de apenas 17,8% y operadores que no hacían caso de las alertas. Esta es la lección más importante para nuestro diseño: **la precisión y la confianza importan más que la sensibilidad cruda**.
- **Los protocolos estructuran todo.** MPDS/ProQA (determinantes Ω-A-B-C-D-E, 1.828 códigos en v13), criteria-based dispatch nórdico (Index: 37 grupos de síntomas × 5 niveles) y estándares NENA NG911 (EIDO JSON, PIDF-LO). Un copiloto creíble mapea "categoría + respuestas clave → prioridad" de forma **determinística y auditable**, no con criterio libre del LLM.
- **Los LLM ya clasifican bien la criticidad a partir de transcripciones,** sobre todo si se les dan guías locales explícitas (Franke et al., ISCRAM 2026, con GPT 5.2 y Claude Sonnet 4.6). Pero la mayoría de los trabajos usan datos simulados o escasos, y casi no hay datasets públicos de llamadas reales, menos todavía en español.
- **El ASR es el eslabón débil en producción.** Hubo WER de 42% en llamadas reales del SAMU brasileño, Prepared reconoce "entre 85 y 90%" de exactitud, y Whisper alucinó frases enteras en ~1% de los segmentos. Como nuestro input es texto, el ruido aparece como lunfardo, frases cortadas, errores de transcripción y datos que se contradicen.
- **Con bloques técnicos maduros, la "salida malformada" ya es un problema resuelto:** structured outputs con constrained decoding, Instructor/Pydantic con reintentos y validadores, y grounding con offsets de cita textual (LangExtract). Lo que sigue abierto es la **corrección semántica** y la **calibración de la confianza**, porque la confianza verbalizada de los LLM tiende a ser sobreconfiada.
- **Para Argentina hay geocodificación pública:** la API Georef (nacional) acepta `calle esquina calle` y `calle entre X y Y`, y USIG cubre CABA. Combinadas con matching difuso y fonético local, resuelven la extracción de direcciones con slang ("a la vuelta de", "pegado al chino").
- **Gobernanza:** el EU AI Act clasifica como **alto riesgo** a los sistemas que *evalúan y clasifican llamadas de emergencia o fijan prioridades de despacho* (Anexo III, 5(d)). La transcripción con keywords queda afuera según el borrador de guías. Ya hubo controversias reales: Seattle usó Corti en vivo sin informarlo y sin evaluación de equidad, y el sindicato de Onondaga demandó por el uso de IA en llamadas no urgentes.
- **Para el prototipo de 72 h:** extracción estructurada con evidencia citada por campo, una prioridad calculada por reglas a partir de un catálogo, un checklist de protocolo dinámico, la validación humana obligatoria antes de enviar la Carta de Llamada y un mock determinístico con las mismas interfaces.

---

## 1. Productos en producción

### 1.1 Específicos de 911 / despacho

**Corti (Dinamarca).** Hace análisis de audio en vivo: ASR seguido de un clasificador que detecta paro cardíaco y, en investigación, ACV. Opera en Copenhagen EMS desde 2018.
- *Evidencia [peer-reviewed]:*
  - En el estudio retrospectivo de 2019 (108.607 llamadas, 918 OHCA), el modelo tuvo menor sensibilidad que los operadores (72,5% vs 84,1%) pero mayor especificidad. También reconocía antes, con una mediana de 44 s vs 54 s, y su PPV fue de 20,9% vs 33,0% ([Blomberg et al., Resuscitation 2019](https://core.ac.uk/download/304613021.pdf)).
  - En el ensayo randomizado de 2018–2019 ([Blomberg et al., JAMA Netw Open 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC7788469)), sobre 169.049 llamadas, el modelo alcanzó 85,0% de sensibilidad vs 77,5% de los operadores. Sin embargo, su PPV fue de 17,8% vs 55,8%, y el reconocimiento humano con alerta no mejoró (93,1% vs 90,5%, p=0,15). Los autores lo atribuyen a la baja adherencia a las alertas, a la poca capacitación y a que el 82% de las alertas habrían sido falsos positivos. El servidor procesó solo el 74,7% de las llamadas por caídas.
  - El análisis de errores de 2023 ("When the machine is wrong", Resuscitation 183) encontró tres causas principales de los OHCA no detectados: el llamante describía otra condición (31%), se reportaba "respira normal" (28%) y había barreras de idioma (23%). Entre los falsos positivos, el 13% eran pacientes con signos evidentes de muerte ([resumen](https://aminer.org/pub/63c52b7890e50fcafd40ad45/when-the-machine-is-wrong-characteristics-of-true-and-false-predictions-of)).
  - En ACV ([Wenstrup et al., npj Digital Medicine 2023](https://pesquisa.bvsalud.org/portal/resource/es/mdl-38114611)), el modelo logró 63,0% de sensibilidad y 24,9% de PPV, frente a 52,7% y 17,1% de los call-takers. Corti tiene los derechos comerciales del modelo y hay conflictos de interés declarados.
- *HITL:* la decisión es del operador, pero el caso Seattle (ver §5) muestra que "el humano decide" no alcanza si no hay transparencia.

**Prepared / Prepared Assist (hoy Axon 911).** Es una capa sobre el call-handling existente, conectada por puerto SPAN, que no reemplaza al CAD. Hace transcripción en vivo, traducción, resúmenes automáticos que se copian al CAD, resaltado de "key insights" y QA ([Colorado PUC demo](https://cpo.soar.com/articles/6164396/Colorado/Prepared-demos-AI-assisted-911-platform-with-live-transcription-locationing-translation-and-QA); [landing](https://prepared911.com/landing/ai-for-911)).
- En la demo reconocieron una exactitud de transcripción "north of 85, getting close to 90%" [vendor/demo].
- Los casos publicados (Baltimore, hangups) no tienen métricas independientes ([Baltimore](https://prepared911.com/case-studies/baltimore-911-call-processing-assistive-ai)) [vendor].
- Axon completó la compra de Prepared el 1/10/2025 y anunció la de Carbyne (USD 625M) el 4/11/2025, para formar "Axon 911" ([anuncio Carbyne](https://www.barchart.com/story/news/35900625/axon-to-acquire-carbyne-uniting-cloud-infrastructure-and-ai-to-redefine-the-911-experience); [blog Prepared](https://www.prepared911.com/blog/axon-911-intelligence-that-starts-the-moment-a-call-is-answered)).
- También se integra con CentralSquare ([nota](https://www.officer.com/command-hq/technology/communications/dispatch-technology/press-release/55091085/centralsquare-partners-with-prepared-911-to-bring-clarity-to-emergency-response)).

**Carbyne (APEX/Universe).** Es call-handling cloud NG911 con traducción bidireccional en vivo (35–37+ idiomas) y "Event Assist", que hace triage y resumen "from call to CAD in seconds" con toma de notas y tagging de contexto ([AI](https://carbyne.com/solutions/ai-that-works-for-you); [triage](https://carbyne.com/ai-powered-911-emergency-call-triage-that-thinks-with-you/)).
- Afirma hasta 20% menos tiempo de manejo y hasta 5 minutos menos en llamadas en otro idioma [vendor].
- Orleans Parish reportó traducción "hasta 70% más rápida" ([OPCD](https://www.opcdla.gov/orleans-parish-communication-district-at-apco-2023/)) [cliente, no auditado].

**RapidSOS HARMONY AI.** Agrega transcripción, traducción y detección de keywords en 190+ idiomas, más resúmenes automáticos de los "critical details" dentro del panel UNITE ([HARMONY](https://rapidsos.com/harmony/)).
- También automatiza líneas no urgentes y alarmas. En el caso Reno, absorbió reclamos por ruido en Año Nuevo, equivalentes a ~15% del volumen ([caso](https://www.casestudies.com/company/rapidsos/case-study/city-of-reno-public-safety-dispatch-handles-up-to-50-of-peak-hour-calls-with-rapidsos)) [vendor].
- Desde 2026 comparte resúmenes y transcripciones entre jurisdicciones ([nota](https://techrepublicnew.blogspot.com/2026/01/rapidsos-introduces-real-time.html)) [prensa].

**Motorola Solutions Assist (VESTA/CommandCentral).** Transcribe y traduce en tiempo real, resalta ubicación, nombres y naturaleza del incidente, mantiene un resumen continuo para supervisores y sugiere "next steps" como crear el incidente o consultar una patente ([blog](https://www.motorolasolutions.com/en_us/blog/here-to-assist); [Dispatcher Assist Suite](https://www.motorolasolutions.com/en_us/ai/assist-dispatcher-suite.html)) [vendor].

**Hexagon HxGN OnCall Dispatch | Smart Advisor (2020).** No trabaja sobre la llamada sino sobre el CAD. Usa agentes analíticos que leen los incidentes cargados y buscan keywords, similitudes, ubicaciones recurrentes y anomalías estadísticas para alertar sobre emergencias complejas o incidentes vinculados. Hexagon declara: "no decision or action is automated" ([producto](https://hexagon.com/products/hxgn-oncall-dispatch-smart-advisor); [GovTech](https://www.govtech.com/biz/hexagon-releases-ai-tool-for-real-time-emergency-analysis.html)).

**Aurelian (AVA + Cora).**
- AVA es un agente de voz para líneas no urgentes. Cuando detecta una emergencia, transfiere al humano junto con los datos del llamante, la ubicación, el tipo de incidente y "key statements" ([TechCrunch](https://techcrunch.com/2025/08/27/911-centers-are-so-understaffed-theyre-turning-to-ai-to-answer-calls)).
- **Cora (dic-2025, SNO911)** es el producto más parecido a nuestro challenge. Es un copiloto en pantalla para llamadas 911 en vivo que "surfaces the exact questions and actions required for each scenario" y funciona como "over-the-shoulder trainer", con el call-taker "100% in control" ([Business Wire](https://www.businesswire.com/news/home/20251216814691/en)). En Summit County (Ohio), un supervisor contó que Cora completa las preguntas que la agencia haría ([News5](https://www.news5cleveland.com/news/local-news/oh-summit/ai-is-now-listening-to-911-calls-in-summit-county-and-helping-dispatchers-in-real-time)).
- No hay evaluación independiente [vendor].

**Hyper.** Es voz IA para líneas no urgentes, usada por ejemplo por el sheriff de San Diego. Las emergencias siguen atendidas por humanos ([GovTech](https://govtech.com/artificial-intelligence/san-diego-county-sheriff-uses-ai-on-non-emergency-calls)).

**Europa / LatAm.** EENA lleva un "AI Special Project" con pilotos en PSAPs europeos. Por ejemplo, Emergencias 112 Andalucía prueba transcripción y traducción con Cestel y Gladia ([EENA](https://eena.org/ai-special-project/)). En Argentina no encontramos productos públicos de IA aplicados a la toma de llamadas 911. La Ciudad de Buenos Aires usa IA en **atención ciudadana no urgente**: Boti, el chatbot complementario al 147, pasó de árboles de decisión a clasificación semántica de consultas ([Caso Boti, GCBA](https://static.buenosaires.gob.ar/sites/default/files/2025-07/Caso_Boti.pdf); [estudio Derechos Digitales](https://www.derechosdigitales.org/en/recursos/boti-study-on-the-natural-language-processing-chatbot-of-the-government-of-the-city-of-buenos-aires-argentina/)).

### 1.2 Patrones adyacentes: "agent assist" de contact center

| Plataforma | Qué hace | Patrón reutilizable |
|---|---|---|
| Google CCAI **Agent Assist** | Knowledge assist (sugiere documentos), *proactive generative knowledge assist* (sugiere preguntas y respuestas durante la llamada), resumen post-llamada con secciones custom y **autoevaluación del resumen** (exactitud, completitud, adherencia) ([docs](https://docs.cloud.google.com/agent-assist/docs/concepts); [release notes](https://docs.cloud.google.com/agent-assist/docs/release-notes)) | Resumen con **secciones fijas** (≈ Carta de Llamada); auto-QA del resumen |
| Amazon Connect **Contact Lens** + **Q in Connect** | Reglas por categoría sobre la transcripción en vivo que disparan alertas al supervisor; Q sugiere respuestas, next-best-action y guías paso a paso ([AWS blog](https://aws.amazon.com/blogs/contact-center/contact-lens-real-time/); [GenAI en Connect](https://aws.amazon.com/blogs/contact-center/increasing-agent-productivity-with-generative-ai-in-amazon-connect)) | **Reglas determinísticas + LLM** combinados; "guided workflows" ≈ checklist de protocolo |
| Microsoft Dynamics 365 Copilot, Genesys, NICE | Resúmenes, sugerencias y QA automatizado (no profundizamos; mismo patrón general) | — |

**Conclusión de la sección:** ningún producto despacha en forma autónoma llamadas de emergencia. Las funciones con mejor adopción son las de bajo riesgo: transcribir, traducir, resumir y recordar preguntas. La clasificación y priorización se presentan siempre como "sugerencia".

---

## 2. Protocolos y estándares de dominio

- **MPDS / ProQA (Priority Dispatch / IAED).** El protocolo se organiza por *chief complaint*: hay un Case Entry con preguntas universales (dirección, callback, consciencia, respiración) y después preguntas de Key Questions específicas. El resultado es un **determinant code** de nivel Ω, A, B, C, D o E (la v13 tiene 1.828 códigos). Los nombres de los niveles son fijos, y cada agencia decide qué recurso y modo de respuesta asigna a cada nivel ([IAED, determinant codes](https://www.iaedjournal.org/determinant-codes); [Wikipedia MPDS](https://en.wikipedia.org/wiki/Medical_Priority_Dispatch_System)). ECHO puede asignarse desde el Case Entry para despachar sin esperar el resto. Además incluye **Post-Dispatch / Pre-Arrival Instructions** estandarizadas. Esa es exactamente la estructura que necesitamos: *categoría → preguntas clave → nivel → instrucciones*.
- **Criteria-Based Dispatch (CBD) nórdico.** Noruega usa el Norsk indeks, y Dinamarca el Danish Index desde 2011, con 37 grupos de síntomas × 5 niveles de urgencia. Es más abierto y conversacional que MPDS ([Andersen et al. 2013](https://link.springer.com/doi/10.1186/1757-7241-21-53)). En OHCA, Richmond (MPDS) y Oslo (CBD) mostraron un reconocimiento similar ([Hardeland et al., Resuscitation 2014](https://read.qxmd.com/read/24525117/comparison-of-medical-priority-dispatch-mpd-and-criteria-based-dispatch-cbd-relating-to-cardiac-arrest-calls)).
- **APCO.** APCO tiene guías y programas de EMD y su propio sistema de protocolos (IntelliComm), además de webinars sobre IA en el 911 ([APCO: lecciones de IA](https://www.apcointl.org/courses/supporting-call-takers-in-the-moment-practical-lessons-from-ai-use-in-9-1-1-webinar-79518/)).
- **NENA NG911 / i3.**
  - NENA-STA-010 define la arquitectura i3.
  - La ubicación viaja como **PIDF-LO** (RFC 4119), en formato civic **CLDXF** (NENA-STA-004).
  - Los *Additional Data* están en NENA-STA-012.
  - Para compartir incidentes entre sistemas existe **EIDO** (NENA-STA-021), un objeto JSON basado en el EIDD conceptual de APCO/NENA ([NENA KB EIDO](https://kb.nena.org/wiki/EIDO_(Emergency_Incident_Data_Object)); [PIDF-LO](https://kb.nena.org/wiki/PIDF-LO_(Presence_Information_Data_Format_-_Location_Object))).
  - Nuestra "Carta de Llamada" puede inspirarse en EIDO: incidente, ubicación, personas, notas y procedencia de cada dato.
- **Mapeo a P1–P4.** No existe un estándar universal. Lo habitual es que la agencia defina una tabla (tipo/subtipo → prioridad), con modificadores según las respuestas clave. Por ejemplo, el pliego federal argentino del Sistema de Atención y Despacho de Emergencias exige "categorizar llamadas y asignar prioridad a cada tipo/subtipo" ([pliego SOFSE](https://contrataciones-publico.sofse.gob.ar/descarga_licitaciones/d0ZuRDIvVVNYRE1wL2tCVlUvODZhUT09)), y el 103 de CABA asigna prioridad por tipo de incidente ([GCBA 103](https://buenosaires.gob.ar/emergencias/103)). Una tabla razonable sería:
  - **P1:** riesgo de vida inminente o en curso (Echo/Delta).
  - **P2:** urgente, con potencial de agravarse (Charlie/Bravo).
  - **P3:** sin riesgo inmediato (Alpha).
  - **P4:** no urgente o derivable (Omega / 147).
  - *Esta equivalencia es una propuesta nuestra, no un estándar.*
- **Argentina / CABA.** El Centro Único de Coordinación y Control articula 911 (seguridad), 107 (SAME), 103 (Emergencias), 108 y la Central de Monitoreo Urbano ([GCBA CUCC](https://buenosaires.gob.ar/seguridad/emergencias/centro-unico-de-coordinacion-y-control)). **No encontramos publicado** el protocolo de triage telefónico del 911 de CABA ni del SAME. No hay que inventarlo: conviene presentar nuestro catálogo como "configurable por la agencia".

---

## 3. Investigación académica

### 3.1 Detección de condiciones específicas (audio → ASR → clasificador)
La línea Copenhague/Corti (§1.1) es la más sólida, porque tiene RCT, análisis de errores y ACV. Sus lecciones:
1. La sensibilidad del modelo no se traduce en mejores decisiones humanas si el PPV es bajo y no hay confianza.
2. Los errores se concentran en descripciones atípicas, en respuestas engañosas como "respira normal" (respiración agónica) y en barreras de idioma.

### 3.2 Clasificación de criticidad / triage con transcripciones
- **Franke, Reuter-Oppermann y Mentler (ISCRAM 2026)** evaluaron GPT 5.2 y Claude Sonnet 4.6 clasificando transcripciones según el esquema ABCDE. Ambos rindieron bien sin guías y **mejoraron notablemente con guías bien diseñadas y adaptables al contexto local**. Los autores advierten que los riesgos son considerables ([ISCRAM](https://ojs.iscram.org/index.php/Proceedings/article/view/228)) [actas].
- **Costa et al., PLOS Digital Health 2023 (SAMU 192, Brasil, portugués)** trabajaron con 182 mil llamadas y anotaron manualmente unas 10 mil. El ASR fine-tuneado (Wav2Vec 2.0) tuvo un **WER de 42%**, y el clasificador NLU con 4 categorías alcanzó un F1 de 74,5%. El entrenamiento usó oraciones sintéticas, los datos no son públicos y los autores insisten en la supervisión humana ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10699611/)) [peer-reviewed]. Es la referencia más cercana a nuestro contexto lingüístico y regional.
- **Whisper + BETO (Perú, español)** clasificó llamadas en accidente, delito o violencia con 95,7% de accuracy. Es una aplicación web con poca descripción de los datos ([UPC](https://cris.upc.edu.pe/es/publications/a-whisper-and-beto-bert-based-web-application-for-classification-/)). Hay que tomarlo con cautela.
- En triage de trauma pediátrico, Buffalo (2026) halló un desempeño del LLM comparable al de clínicos. Además, ver la salida del LLM después de un error **triplicó las chances de que los humanos corrigieran su decisión** ([UB](https://www.buffalo.edu/news/releases/2026/07/Trauma-triage-can-LLM-help-UB-Surgery.html)) [comunicado universitario]. Es un argumento a favor de mostrar la sugerencia como "segunda opinión".
- Una revisión de NLP en emergencias señala que la mayoría de los estudios tratan el triage como clasificación multiclase **ignorando su ordinalidad**, y que evalúan con datos post-hoc en lugar de la información disponible en el momento ([arXiv 2608.23627](https://arxiv.org/pdf/2608.23627)) [preprint].

### 3.3 LLMs para despacho y extracción de información
- **DispatchMAS (J. Biomed. Inform.; [arXiv 2510.21228](https://arxiv.org/html/2510.21228v1))** simula llamadas EMD con dos agentes, llamante y operador, sobre una taxonomía de 32 chief complaints y 6 fases (intake, escena, despacho, actualizaciones, pre-arrival, cierre). En cada turno, un clasificador liviano elige el chief complaint o "Lack of Information" y se **inyecta por recuperación el protocolo** correspondiente. En la evaluación de médicos, contactó al agente correcto el 94% de las veces y dio consejo cuando hacía falta el 91%. Su limitación: todo es simulado. **Ideas transferibles:** la clase explícita "falta información" y el RAG de protocolo por categoría.
- **Otal y Canbaz (2024, [arXiv 2402.10908](https://arxiv.org/abs/2402.10908))** proponen con Llama 2 un copiloto que extrae datos del llamante, sugiere instrucciones y dispara workflows. Es más propuesta que evaluación.
- **Sim911** y trabajos de entrenamiento simulado de operadores con LLM aparecen citados en DispatchMAS. No los verificamos en detalle.

### 3.4 ASR en llamadas de emergencia
- Las llamadas tienen banda telefónica, ruido, estrés, dialectos y hablantes no nativos. Ya lo señalaba el sistema NineOneOne/Ayudame para llamadas 911 en español ([LREC 2008](https://aclanthology.org/www.mt-archive.info/LREC-2008-Nallasamy.pdf)).
- Corti entrenó un ASR propio en danés con 173 h de llamadas anotadas.
- **Las alucinaciones del ASR** son un riesgo: Whisper inventó frases completas en ~1% de los segmentos, y el 38% de ellas tenían contenido dañino, con violencia y falsas asociaciones. Afecta más a personas con pausas largas, como en la afasia ([Koenecke et al., FAccT 2024](https://arxiv.org/html/2402.08021)).
- **Implicancia para nosotros:** aunque recibimos texto, tenemos que asumir que **la transcripción puede tener errores o contenido inventado** y mostrar siempre la cita de origen.

### 3.5 Datasets
No encontramos datasets públicos de transcripciones reales de 911/112 en español. Lo que hay:
- un modelo de clasificación de emergencias en español en Hugging Face, con acceso restringido ([UDA-LIDI](https://huggingface.co/UDA-LIDI/roberta_emergency_classification));
- tweets de emergencia de Ecuador ([UrbangEnCy](https://pmc.ncbi.nlm.nih.gov/articles/PMC7804594/));
- datos privados en portugués.

Para el challenge, lo realista es **crear un set propio de transcripciones sintéticas** con lunfardo, ruido y datos incompletos, al estilo DispatchMAS.

---

## 4. Bloques técnicos para nuestro diseño

### 4.1 Extracción con esquema
- **Structured outputs con constrained decoding.** OpenAI introdujo en ago-2024 el *strict mode*, que enmascara los tokens inválidos y garantiza que la salida cumpla el schema, con un subconjunto de JSON Schema que exige `additionalProperties:false`. Que la salida cumpla el schema **no garantiza que sea correcta** ([resumen](https://www.respan.ai/articles/openai-structured-outputs-vs-json-mode)). Anthropic y Gemini ofrecen mecanismos análogos de tool use o JSON schema.
- **Outlines** (dottxt) hace generación guiada por regex/JSON Schema con máquinas de estado finito, útil con modelos locales (Willard & Louf, 2023, "Efficient Guided Generation for Large Language Models", [arXiv 2307.09702](https://arxiv.org/abs/2307.09702)).
- **Instructor** usa Pydantic. Cuando falla la validación, reenvía el error al modelo para que corrija (`max_retries`), cubre también los errores de JSON y admite validadores con `context` en tiempo de ejecución, **por ejemplo para verificar que una cita exista en el texto fuente** ([docs](https://python.useinstructor.com/concepts/reask_validation/)). En TypeScript el equivalente es **Zod** con `safeParse` y un reintento.
- **Patrón robusto:** primero parse estricto. Si falla, se intenta una reparación (extraer el bloque JSON y corregir comillas). Si vuelve a fallar, un reintento con el error. Si todo falla, el *fallback* determinístico (mock/reglas), y la UI se degrada con un aviso: nunca se rompe la pantalla.

### 4.2 Grounding y control de alucinaciones
- **Citas con offsets:** LangExtract (Google) asocia cada extracción a sus *character offsets* en el texto fuente. Las extracciones que no se pueden ubicar quedan con `char_interval=None` y **se pueden descartar** ([GitHub](https://github.com/google/langextract); [blog](https://developers.googleblog.com/en/introducing-langextract-a-gemini-powered-information-extraction-library/)). Es directamente aplicable: cada campo (`calle`, `altura`, `heridos`) lleva `evidence: "texto literal"` y se verifica por substring o fuzzy match contra la transcripción.
- **Otras técnicas conocidas:** self-consistency (muestrear N veces y votar), SelfCheckGPT ([arXiv 2303.08896](https://arxiv.org/abs/2303.08896)), Chain-of-Verification ([arXiv 2309.11495](https://arxiv.org/abs/2309.11495)) y la regla "no está en el texto → null/UNKNOWN", con valores `desconocido` explícitos en el schema.
- **Las instrucciones de seguridad nunca deben generarse libremente.** Hay que **recuperarlas de un catálogo curado** por categoría, como hace MPDS con sus Pre-Arrival Instructions y DispatchMAS con su RAG de protocolo.

### 4.3 Confianza y calibración
- La confianza verbalizada de los LLM es **sobreconfiada** en todos los tamaños de modelo ([arXiv 2412.14737](https://arxiv.org/pdf/2412.14737)). Tian et al. 2023 encuentran que la confianza verbalizada calibra mejor que las probabilidades crudas en modelos RLHF, y mejora si el modelo considera varias hipótesis antes ([arXiv 2305.14975](https://arxiv.org/pdf/2305.14975)).
- Para el prototipo conviene una **confianza compuesta y explicable**, sin depender del número que diga el LLM:
  - ¿hay evidencia verificada en el texto?
  - ¿la dirección geocodificó?
  - ¿coinciden el LLM y las reglas?
  - ¿hay contradicciones?
- La UI la muestra en 3 niveles (confirmado / probable / dudoso), no como un porcentaje falso.

### 4.4 Direcciones en español rioplatense y geocodificación
- **Georef API (nacional, gratuita, sin auth):** `GET https://apis.datos.gob.ar/georef/api/v2.0/direcciones?direccion=...`. Acepta `calle altura`, `calle esquina calle`, `calle entre X y Y` y piso/depto. Devuelve calle normalizada con id, `calle_cruce_1/2`, altura, `nomenclatura` y lat/lon aproximada. Su parser es open source (*georef-ar-address*) ([doc](https://www.argentina.gob.ar/georef/normalizacion-de-direcciones)).
- **USIG (GCBA)** es el normalizador oficial de CABA, con validación de calle contra el callejero y de altura o intersección ([manual](https://usig.buenosaires.gob.ar/manual_normalizador_de_direcciones_USIG.pdf)). No verificamos endpoints actuales.
- **libpostal** es un parser/normalizador multilenguaje entrenado con OpenStreetMap. Es útil como alternativa offline, pero no maneja expresiones como "a la vuelta de".
- **Matching difuso y fonético** contra un callejero local en JSON. Se puede usar `rapidfuzz` o `fuse.js`, con normalización de abreviaturas (Av., Gral., Pte.) y apodos o nombres viejos ("Santa Fe" → "Av. Santa Fe", "Rivadavia", "la 9 de Julio"). Una clave fonética simple para español (b/v, s/z/c, ll/y, h muda) cubre errores típicos de ASR o tipeo.
- **Patrón:** el LLM extrae los componentes junto con la cita textual. Después, una capa determinística normaliza y geocodifica, y si hay ambigüedad la UI muestra candidatos y una **pregunta sugerida** ("¿Entre qué calles?").

### 4.5 Few-shot y retrieval con catálogos chicos
Con unas 20–40 categorías y su protocolo, lo más simple es incluir el catálogo completo en el prompt o hacer RAG trivial por keywords, siguiendo el enfoque de DispatchMAS. Las guías explícitas mejoran el desempeño (Franke et al.). Además, hay que forzar `category` como `enum` del schema.

### 4.6 Extracción incremental
Los productos (Prepared, Motorola, Cora) actualizan transcripción, resumen y preguntas sugeridas a medida que avanza la llamada. Para el prototipo alcanza con **re-extraer sobre la transcripción acumulada** con debounce y **mergear con un estado previo**. El merge tiene que respetar las ediciones del operador (lo que el humano tocó queda bloqueado) y marcar las contradicciones nuevas ("antes dijo Corrientes 1200, ahora dice 1500").

### 4.7 UX para operadores bajo estrés
- **La alarma ignorada es el modo de falla documentado.** Pasó en el RCT de Corti, y en CPOE los overrides de alertas van de 46% a 96% ([Poly et al., JMIR MI 2020](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7400042/)). Pocas alertas, y solo las de alta precisión.
- **Automation bias:** los factores que lo modulan son la experiencia, la confianza y el diseño del sistema de soporte ([Goddard et al., JAMIA 2012](https://openaccess.city.ac.uk/id/eprint/3005/1/Goddard,_Kate.pdf)). Una mitigación es mostrar la evidencia y exigir una confirmación activa en los campos críticos.
- **Las tecnologías aditivas suelen aumentar la carga cognitiva** ([NIST IR 8295](https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8295.pdf)). Un estudio etnográfico de 2026 sugiere apuntar la asistencia "no intrusiva" a la primera decisión del flujo ([arXiv 2609.07705](https://arxiv.org/abs/2609.07705)). Otro trabajo encontró que distintas herramientas de despacho con igual velocidad y error difieren en carga percibida (SUS/NASA-TLX) ([poster CrowdCAD](https://berkeleymrc.github.io/jcems-event-dispatch-poster/pdf/jcems_poster.pdf)).
- **Principios para la UI:**
  - una sola pantalla y jerarquía fija (ubicación → qué pasa → prioridad → próxima pregunta);
  - pocas palabras y tipografía grande;
  - teclado primero;
  - la "próxima pregunta" siempre visible;
  - las instrucciones en formato para **leer en voz alta**, frases cortas y numeradas;
  - nada se envía sin validación humana.

---

## 5. Riesgos y gobernanza

- **EU AI Act, Anexo III punto 5(d).** Son de alto riesgo los sistemas que "evaluar y clasificar llamadas de emergencia" o despachar o priorizar servicios de primera respuesta, incluido el triage de pacientes ([texto](https://artificialintelligenceact.eu/annex/3/)). Según el borrador de guías de la Comisión, la transcripción por keywords que no evalúa ni clasifica la llamada **queda fuera** ([McCann FitzGerald](https://www.mccannfitzgerald.com/knowledge/technology-and-innovation/essential-services-spotlight-eu-ai-act-draft-guidelines-on-high-risk-ai-classification)). Fuentes secundarias indican que el *Digital Omnibus* habría postergado las obligaciones del Anexo III a dic-2027 (no verificado en el DOUE). *Implicancia:* nuestra sugerencia de categoría y prioridad caería en alto riesgo en la UE, con obligaciones de supervisión humana, logging, gestión de riesgos y calidad de datos. Diseñar con eso en mente es buen product sense también para Argentina.
- **Seattle / Corti (2023–2026).** La IA escuchaba todas las llamadas médicas al 911 y sugería derivar a algunos llamantes a una línea de enfermería. No se informaba a los llamantes y la evaluación de equidad (acentos, discapacidad, habla bajo estrés) recomendada en 2019 nunca se hizo. Expertos piden suspenderla y auditarla ([JEMS / Seattle Times](https://www.jems.com/news/internal-report-raised-concerns-about-ai-use-on-seattle-ca-911-calls-went-ignored/)) [prensa].
- **Onondaga County (NY).** El sindicato de operadores demandó por el uso de IA en llamadas no urgentes, por violar el convenio colectivo y la ley estatal ([Officer.com](https://www.officer.com/command-hq/technology/communications/dispatch-technology/news/55411676/onondaga-county-911-dispatchers-union-sues-over-ai-call-handling-system)).
- **Otros riesgos señalados:** sesgos que sobre-asignan respuesta policial, responsabilidad legal, y la ausencia casi total de métricas públicas y de evaluaciones independientes de los vendors ([Stateline](https://www.stateline.org/ai-bots-are-helping-911-dispatchers-with-their-workload/)).
- **Por qué el humano sigue en el loop:**
  1. La evidencia (RCT de Corti) muestra que el valor está en la interacción humano-IA, no en el modelo solo.
  2. Los errores del modelo se concentran en casos atípicos y en barreras de idioma.
  3. Hay responsabilidad legal y regulación.
  4. En nuestro dominio, además, **el call-taker no despacha**: el despachador del CAD es un segundo humano en la cadena.

---

## 6. Tabla comparativa

| Sistema | Qué hace | Input | Técnica IA | Human-in-the-loop | Evidencia |
|---|---|---|---|---|---|
| **Corti** (Copenhague, Seattle) | Detecta OHCA / ACV en vivo; QA | Audio | ASR propio + clasificador | Alerta; decide el operador | **Peer-reviewed + RCT**: más sensibilidad que humanos, sin mejora del reconocimiento humano en el RCT |
| **Prepared Assist / Axon 911** | Transcripción, traducción, resumen al CAD, key insights, QA | Audio (SPAN) | ASR + LLM | Operador copia/edita al CAD | Vendor; exactitud ASR "85–90%" (demo) |
| **Carbyne APEX / Event Assist** | Call-handling NG911, traducción bidireccional, triage y resumen | Audio, video, chat, ubicación | ASR, MT, LLM | Sugerencia | Vendor (−20% de tiempo de manejo) |
| **RapidSOS HARMONY** | Transcripción, keywords, resúmenes, líneas no urgentes, interoperabilidad | Audio + datos de dispositivo | ASR, NLU, LLM | Sugerencia; IA autónoma solo en no urgentes | Vendor (caso Reno) |
| **Motorola Assist** | Transcripción, traducción, keywords, resumen continuo, next steps | Audio | ASR + LLM | Sugerencia | Vendor |
| **Aurelian Cora / AVA** | Cora: preguntas de protocolo en vivo; AVA: voz IA no urgente con handoff estructurado | Audio | ASR + LLM + protocolo | Cora: 100% humano; AVA: transfiere emergencias | Vendor |
| **Hexagon Smart Advisor** | Detecta patrones e incidentes vinculados en el CAD | Registros CAD | Estadística/ML, agentes | "No decision automated" | Vendor |
| **Google Agent Assist / Amazon Contact Lens + Q** | Sugerencias, guías, resúmenes por secciones, alertas por reglas | Audio/chat | ASR + LLM + reglas | Agente decide | Vendor (dominio comercial) |
| **DispatchMAS** (académico) | Simulación EMD con protocolo recuperado por categoría | Texto simulado | Multi-agente LLM + RAG | N/A (simulación) | Preprint/journal; evaluado por médicos |
| **Franke et al. ISCRAM 2026** | Clasificación de criticidad ABCDE | Transcripciones | LLM + guías | Propone soporte | Actas; "buen desempeño", mejora con guías |
| **Costa et al. SAMU (BR)** | ASR + clasificación de 4 chief complaints | Audio portugués | Wav2Vec2 + NLU | Supervisión humana requerida | Peer-reviewed; WER 42%, F1 74,5% |
| **Nuestro copiloto** | Ubicación, categoría, P1–P4, instrucciones, checklist, Carta de Llamada | Texto | LLM con schema + reglas + catálogo + mock | Validación obligatoria; despacha otro humano | Prototipo; eval con set sintético propio |

---

## 7. Qué tomamos para nuestro copiloto

### Prioridad alta (implementable en 72 h)

1. **Extracción con schema estricto y evidencia por campo.** Usar Pydantic/Zod con `enum` para categorías, `null`/`desconocido` explícitos y `evidence_quote` por campo. Un validador verifica que la cita exista en la transcripción (exacta o fuzzy ≥ umbral), y si no existe, el campo se descarta o queda marcado "sin evidencia". El patrón viene de LangExtract y de los validadores con `context` de Instructor.
2. **Prioridad calculada por reglas, no por el LLM.** El LLM extrae hechos (consciente, respira, armas, fuego, cantidad de víctimas, etc.) y sugiere categoría. Una tabla determinística **categoría + respuestas clave → P1–P4**, al estilo de los determinantes MPDS, calcula la prioridad y muestra el "por qué" ("P1 porque: no respira (cita)"). Es auditable, testeable, y el mock offline queda casi igual al modo real.
3. **Catálogo curado de protocolos.** Cada categoría trae su lista de preguntas clave (checklist) y sus instrucciones pre-arribo **fijas y en texto para leer en voz alta**, en línea con MPDS PAI y DispatchMAS RAG. El LLM solo marca qué preguntas ya están respondidas (con cita) y cuál es la siguiente. **Nunca redacta instrucciones de seguridad.**
4. **Pipeline resiliente con degradación elegante:** parse estricto, después reparación, después reintento con el error y por último fallback a reglas/mock. Interfaz `Extractor` con implementación `LLMExtractor` y `MockExtractor` (regex + diccionario de lunfardo/sinónimos + callejero). Hay que mostrar en UI qué motor respondió y tener tests de golden transcripts sobre ambos.
5. **Ubicación como subsistema propio.** Extraer calle, altura, entrecalles, esquina y referencias ("frente a la plaza", "al lado del chino"). Después normalizar contra un callejero local con fuzzy y fonética, y opcionalmente consultar Georef/USIG. Ante ambigüedad o falta de dato, la UI muestra candidatos y la **pregunta sugerida**, y la ubicación es el primer bloque visual.
6. **Validación humana obligatoria y Carta de Llamada estilo EIDO.** Cada campo puede estar sugerido, confirmado o editado, y lo que el humano edita queda bloqueado frente a re-extracciones. El botón "Enviar al despachador" se habilita solo con ubicación y categoría confirmadas. La carta lleva la procedencia (IA/humano), las citas y un timestamp, y queda log de auditoría.
7. **Confianza explicable en 3 niveles** (evidencia + geocodificación + acuerdo reglas/LLM + contradicciones), en lugar de porcentajes verbalizados. Las alertas se reservan para pocos casos de alta precisión, como las señales de P1 y las contradicciones, para evitar el patrón "alerta ignorada" del RCT de Corti.
8. **Set de evaluación sintético** de 15–30 transcripciones con lunfardo ("un pibe", "le dieron un puntazo", "está re mal"), ruido, cortes, datos contradictorios y llamadas no urgentes que deberían ir al 147. Métricas por campo (exactitud de ubicación, categoría, prioridad, % de campos con evidencia válida, tasa de JSON inválido recuperado).

### Prioridad media (si sobra tiempo)
- Re-extracción incremental con debounce, simulando la llamada "en vivo" turno a turno con un *replay*, más detección de contradicciones entre turnos.
- Self-consistency: dos o tres extracciones y comparar la categoría. Si no hay acuerdo, se marca "dudoso".
- Atajos de teclado y modo de alto contraste.
- Derivación sugerida a 147 cuando el caso no es una emergencia.

### Solo como trabajo futuro (mencionar, no construir)
- ASR en vivo (Whisper o similar fine-tuneado a la telefonía local), con mitigación de alucinaciones de ASR y diarización.
- Traducción en vivo para llamantes no hispanohablantes.
- Integración NG911: ubicación del dispositivo vía PIDF-LO o datos tipo RapidSOS, y export EIDO real al CAD.
- Detectores especializados (paro cardíaco, ACV) entrenados con datos locales, validados con un RCT. Conviene recordar la lección de Corti: el impacto depende de la adopción humana.
- Evaluación de equidad (acentos, discapacidades, estrés), monitoreo de drift y QA post-llamada automatizado.
- Gobernanza: registro de decisiones, transparencia al ciudadano y alineación con marcos de IA de alto riesgo (EU AI Act Anexo III 5(d) como referencia).
- Detección de incidentes vinculados (varias llamadas del mismo evento), al estilo Hexagon Smart Advisor.

---

## Referencias

**Productos / vendor**
- Prepared: [AI for 911](https://prepared911.com/landing/ai-for-911) · [Axon 911 blog](https://www.prepared911.com/blog/axon-911-intelligence-that-starts-the-moment-a-call-is-answered) · [Baltimore case study](https://prepared911.com/case-studies/baltimore-911-call-processing-assistive-ai) · [Colorado PUC demo](https://cpo.soar.com/articles/6164396/Colorado/Prepared-demos-AI-assisted-911-platform-with-live-transcription-locationing-translation-and-QA) · [CentralSquare partnership](https://www.officer.com/command-hq/technology/communications/dispatch-technology/press-release/55091085/centralsquare-partners-with-prepared-911-to-bring-clarity-to-emergency-response)
- Axon–Carbyne: [press release](https://www.barchart.com/story/news/35900625/axon-to-acquire-carbyne-uniting-cloud-infrastructure-and-ai-to-redefine-the-911-experience)
- Carbyne: [AI](https://carbyne.com/solutions/ai-that-works-for-you) · [AI triage](https://carbyne.com/ai-powered-911-emergency-call-triage-that-thinks-with-you/) · [translation PR](https://carbyne.com/resources/press/carbynes-apex-emergency-call-handling-system-now-offers-ai-driven-two-way-translation-capabilities-to-improve-9-1-1-response-time-and-accuracy/) · [OPCD](https://www.opcdla.gov/orleans-parish-communication-district-at-apco-2023/)
- RapidSOS: [HARMONY](https://rapidsos.com/harmony/) · [Reno case](https://www.casestudies.com/company/rapidsos/case-study/city-of-reno-public-safety-dispatch-handles-up-to-50-of-peak-hour-calls-with-rapidsos) · [Interoperability 2026](https://techrepublicnew.blogspot.com/2026/01/rapidsos-introduces-real-time.html)
- Motorola: [Here to Assist](https://www.motorolasolutions.com/en_us/blog/here-to-assist) · [Dispatcher Assist Suite](https://www.motorolasolutions.com/en_us/ai/assist-dispatcher-suite.html)
- Hexagon: [Smart Advisor](https://hexagon.com/products/hxgn-oncall-dispatch-smart-advisor) · [GovTech](https://www.govtech.com/biz/hexagon-releases-ai-tool-for-real-time-emergency-analysis.html)
- Aurelian: [Cora PR](https://www.businesswire.com/news/home/20251216814691/en) · [News5 Summit County](https://www.news5cleveland.com/news/local-news/oh-summit/ai-is-now-listening-to-911-calls-in-summit-county-and-helping-dispatchers-in-real-time) · [TechCrunch](https://techcrunch.com/2025/08/27/911-centers-are-so-understaffed-theyre-turning-to-ai-to-answer-calls)
- Hyper: [GovTech San Diego](https://govtech.com/artificial-intelligence/san-diego-county-sheriff-uses-ai-on-non-emergency-calls)
- EENA: [AI Special Project](https://eena.org/ai-special-project/)
- Google: [Agent Assist concepts](https://docs.cloud.google.com/agent-assist/docs/concepts) · [release notes](https://docs.cloud.google.com/agent-assist/docs/release-notes)
- AWS: [Contact Lens real-time](https://aws.amazon.com/blogs/contact-center/contact-lens-real-time/) · [GenAI in Connect](https://aws.amazon.com/blogs/contact-center/increasing-agent-productivity-with-generative-ai-in-amazon-connect)
- GCBA: [Caso Boti](https://static.buenosaires.gob.ar/sites/default/files/2025-07/Caso_Boti.pdf) · [CUCC](https://buenosaires.gob.ar/seguridad/emergencias/centro-unico-de-coordinacion-y-control) · [103](https://buenosaires.gob.ar/emergencias/103) · [Derechos Digitales sobre Boti](https://www.derechosdigitales.org/en/recursos/boti-study-on-the-natural-language-processing-chatbot-of-the-government-of-the-city-of-buenos-aires-argentina/)

**Protocolos / estándares**
- IAED: [Determinant codes](https://www.iaedjournal.org/determinant-codes) · [Wikipedia MPDS](https://en.wikipedia.org/wiki/Medical_Priority_Dispatch_System)
- Andersen et al. 2013, Danish Index: [SJTREM](https://link.springer.com/doi/10.1186/1757-7241-21-53)
- Hardeland et al. 2014, MPDS vs CBD: [Resuscitation](https://read.qxmd.com/read/24525117/comparison-of-medical-priority-dispatch-mpd-and-criteria-based-dispatch-cbd-relating-to-cardiac-arrest-calls)
- NENA: [EIDO](https://kb.nena.org/wiki/EIDO_(Emergency_Incident_Data_Object)) · [PIDF-LO](https://kb.nena.org/wiki/PIDF-LO_(Presence_Information_Data_Format_-_Location_Object))
- APCO: [webinar IA en 911](https://www.apcointl.org/courses/supporting-call-takers-in-the-moment-practical-lessons-from-ai-use-in-9-1-1-webinar-79518/)

**Académicos**
- Blomberg et al. 2019, *Machine learning as a supportive tool to recognize cardiac arrest in emergency calls*, Resuscitation: [PDF](https://core.ac.uk/download/304613021.pdf)
- Blomberg et al. 2021, *Effect of Machine Learning on Dispatcher Recognition of OHCA…: A Randomized Clinical Trial*, JAMA Netw Open: [PMC7788469](https://pmc.ncbi.nlm.nih.gov/articles/PMC7788469) · [NCT04219306](https://clinicaltrials.gov/study/NCT04219306)
- Blomberg et al. 2023, *When the machine is wrong…*, Resuscitation 183: [registro](https://aminer.org/pub/63c52b7890e50fcafd40ad45/when-the-machine-is-wrong-characteristics-of-true-and-false-predictions-of)
- Wenstrup et al. 2023, stroke recognition, npj Digit Med: [registro](https://pesquisa.bvsalud.org/portal/resource/es/mdl-38114611)
- Franke, Reuter-Oppermann, Mentler 2026, *Potential of LLMs in Supporting Call-taking Processes of Emergency Dispatch Centers*, ISCRAM: [link](https://ojs.iscram.org/index.php/Proceedings/article/view/228)
- Li, Yu, Wang et al., *DispatchMAS: Fusing taxonomy and artificial intelligence agents for emergency medical services*: [arXiv 2510.21228](https://arxiv.org/html/2510.21228v1)
- Otal & Canbaz 2024, *LLM-Assisted Crisis Management…*: [arXiv 2402.10908](https://arxiv.org/abs/2402.10908)
- Costa et al. 2023, *AI-based approach for transcribing and classifying unstructured emergency call data*, PLOS Digit Health: [PMC10699611](https://pmc.ncbi.nlm.nih.gov/articles/PMC10699611/)
- Whisper + BETO (UPC Perú): [link](https://cris.upc.edu.pe/es/publications/a-whisper-and-beto-bert-based-web-application-for-classification-/)
- *From Triage to Discharge: A Survey of NLP Tasks… in the Emergency Department*: [arXiv 2608.23627](https://arxiv.org/pdf/2608.23627)
- Koenecke et al. 2024, *Careless Whisper: Speech-to-Text Hallucination Harms*, FAccT: [arXiv 2402.08021](https://arxiv.org/html/2402.08021)
- Nallasamy et al. 2008, *NineOneOne*, LREC: [PDF](https://aclanthology.org/www.mt-archive.info/LREC-2008-Nallasamy.pdf)
- Wilson et al. 2026, *Situated Action in Pre-Hospital Critical Care Dispatch…*: [arXiv 2609.07705](https://arxiv.org/abs/2609.07705)
- UB trauma triage LLM 2026: [comunicado](https://www.buffalo.edu/news/releases/2026/07/Trauma-triage-can-LLM-help-UB-Surgery.html)
- Goddard, Roudsari, Wyatt, automation bias (JAMIA 2012; tesis): [PDF](https://openaccess.city.ac.uk/id/eprint/3005/1/Goddard,_Kate.pdf)
- Poly et al. 2020, overridden alerts, JMIR MI: [PMC7400042](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7400042/)
- NIST IR 8295 (PSCR, usabilidad en seguridad pública): [PDF](https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8295.pdf)
- CrowdCAD dispatch tools (poster): [PDF](https://berkeleymrc.github.io/jcems-event-dispatch-poster/pdf/jcems_poster.pdf)
- *On Verbalized Confidence Scores for LLMs*: [arXiv 2412.14737](https://arxiv.org/pdf/2412.14737) · Tian et al. 2023, *Just Ask for Calibration*: [arXiv 2305.14975](https://arxiv.org/pdf/2305.14975)
- Manakul et al. 2023, SelfCheckGPT: [arXiv 2303.08896](https://arxiv.org/abs/2303.08896) · Dhuliawala et al. 2023, Chain-of-Verification: [arXiv 2309.11495](https://arxiv.org/abs/2309.11495) · Willard & Louf 2023, Outlines: [arXiv 2307.09702](https://arxiv.org/abs/2307.09702)

**Herramientas**
- Instructor, reask/validation: [docs](https://python.useinstructor.com/concepts/reask_validation/)
- LangExtract: [GitHub](https://github.com/google/langextract) · [blog](https://developers.googleblog.com/en/introducing-langextract-a-gemini-powered-information-extraction-library/)
- OpenAI structured outputs vs JSON mode (secundaria): [link](https://www.respan.ai/articles/openai-structured-outputs-vs-json-mode)
- Georef: [normalización de direcciones](https://www.argentina.gob.ar/georef/normalizacion-de-direcciones) · USIG: [manual normalizador](https://usig.buenosaires.gob.ar/manual_normalizador_de_direcciones_USIG.pdf)

**Riesgos / regulación**
- EU AI Act Anexo III: [texto](https://artificialintelligenceact.eu/annex/3/) · [McCann FitzGerald, borrador de guías](https://www.mccannfitzgerald.com/knowledge/technology-and-innovation/essential-services-spotlight-eu-ai-act-draft-guidelines-on-high-risk-ai-classification)
- Seattle/Corti: [JEMS](https://www.jems.com/news/internal-report-raised-concerns-about-ai-use-on-seattle-ca-911-calls-went-ignored/)
- Onondaga union lawsuit: [Officer.com](https://www.officer.com/command-hq/technology/communications/dispatch-technology/news/55411676/onondaga-county-911-dispatchers-union-sues-over-ai-call-handling-system)
- Stateline, AI bots en 911: [link](https://www.stateline.org/ai-bots-are-helping-911-dispatchers-with-their-workload/)

> **No verificado / pendiente:** protocolo de triage telefónico vigente del 911 CABA y SAME 107; endpoints actuales de la API USIG; fecha exacta del Digital Omnibus en el DOUE; métricas independientes de cualquier vendor 911 (no encontramos ninguna).
