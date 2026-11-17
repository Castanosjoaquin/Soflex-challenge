// Typed client for the backend API. Shapes mirror the Pydantic models in backend/app.

export type Priority = 'P1' | 'P2' | 'P3' | 'P4'
export type Line = '911' | '107' | '103' | '147' | 'app'
export type Speaker = 'operador' | 'llamante'

export interface Health {
  status: string
  provider: 'mock' | 'openai_compat'
  catalog_size: number
}

export interface ParsedTurn {
  speaker: Speaker
  text: string
  /** Pause before this turno during live replay (demo calls); a default applies otherwise. */
  delay_ms?: number | null
}

export interface SampleCall {
  id: string
  /** Demo calls are the extended, multi-turno ones; dataset ones are the 30 cases as given. */
  kind: 'demo' | 'dataset'
  title: string
  line: Line
  category: string
  subcategory: string
  priority: Priority
  transcript: string
  turns: ParsedTurn[]
}

export interface Turn extends ParsedTurn {
  index: number
  at_ms: number
}

export interface Evidence {
  turn_index: number
  start: number
  end: number
  quote: string
}

export type NumberKind = 'exacta' | 'al' | 'esquina' | 'km' | 'sn'
export type Confidence = 'confirmado' | 'probable' | 'a_confirmar'

export interface Location {
  said: string
  evidence: Evidence[]
  street: string | null
  street_official: string | null
  number: { value: number | null; kind: NumberKind } | null
  cross_streets: string[]
  /** Official names of the cross streets, or as said when not in the list. */
  cross_streets_official: string[]
  landmark: string | null
  /** Every official street the name fits, when it fits more than one. */
  candidates: string[]
  confidence: Confidence
  source: Source
}

export type SignalAnswer = 'si' | 'no' | 'no_sabe'
export type Source = 'reglas' | 'ia' | 'operador'

/** What the other lector read for the same señal, when the two disagree. */
export interface SignalAlternative {
  value: SignalAnswer
  evidence: Evidence
  source: Source
}

export interface SignalValue {
  signal_id: string
  value: SignalAnswer
  evidence: Evidence | null
  source: Source
  confidence: Confidence
  /** Set when the lectores disagree on the value: the señal stays a confirmar. */
  alternative: SignalAlternative | null
}

export interface Incident {
  category: string
  subtype: string | null
  evidence: Evidence[]
  confidence: Confidence
  source: Source
}

/** The lectores point to different tipos; meanwhile `incident` is the more urgent option. */
export interface TypeDispute {
  options: Incident[]
}

export interface PriorityReason {
  signal_id: string
  value: SignalAnswer
  evidence: Evidence | null
}

export interface PriorityAssessment {
  level: Priority
  /** The rule of the tabla that fired: the porqué in one line. */
  rule: string
  reasons: PriorityReason[]
  overridden_by_operator: { from_level: Priority | null; reason: string } | null
}

export interface NextQuestion {
  id: string
  text: string
  signal_ids: string[]
}

export type QuestionStatus = 'pendiente' | 'pre_marcada' | 'respondida' | 'salteada'

export interface ChecklistItem {
  question_id: string
  text: string
  signal_id: string
  critical: boolean
  status: QuestionStatus
  value: SignalAnswer | null
  evidence: Evidence | null
  source: Source | null
}

/** An instrucción of the protocol, written beforehand: the IA never writes one. */
export interface InstructionItem {
  instruction_id: string
  text: string
  /** Only the active instrucción crítica: at most one per llamada. */
  critical: boolean
  read: boolean
}

export interface Catalog {
  signals: { id: string; label: string; question_hint: string }[]
  types: { id: string; label: string }[]
  subtypes: { id: string; category: string; label: string; reclamo: boolean }[]
}

export type StageId = 'ubicar' | 'que_pasa' | 'preguntas' | 'derivar' | 'instrucciones'
export type StageStatus = 'hecha' | 'actual' | 'pendiente'

export interface CallState {
  call_id: string
  line: Line
  mode: 'ia' | 'reglas' | 'simulado'
  sample_id: string | null
  turns: Turn[]
  location: Location | null
  incident: Incident | null
  type_dispute: TypeDispute | null
  signals: SignalValue[]
  priority: PriorityAssessment | null
  checklist: ChecklistItem[]
  skipped_questions: string[]
  next_question: NextQuestion | null
  /** In reading order, the active crítica first. */
  instructions: InstructionItem[]
  critical_instruction: InstructionItem | null
  read_instructions: string[]
  /** The operador's own notas, in order: the only free text. They go to the Carta. */
  notes: string[]
  /** `alert`: the llamada already needs what this etapa lacks (① without ubicación). */
  stages: { id: StageId; status: StageStatus; alert: boolean }[]
  carta: Carta
  /** Ubicación and tipo confirmed: the Carta can be derivada. */
  can_derive: boolean
  derived: boolean
  ampliaciones: Ampliacion[]
  /** Contradicciones and señales de P1 for the operador to resolve, in order of appearance. */
  avisos: Aviso[]
}

export type AvisoKind = 'contradiccion' | 'senal_p1'
export type AvisoStatus = 'pendiente' | 'aceptado' | 'mantenido'
export type Resolution = 'aceptar' | 'mantener'

/** «Antes dijo X, ahora dice Y»: the confirmed dato stays until the operador decides. */
export interface Aviso {
  id: string
  kind: AvisoKind
  /** "location", "incident", a señal id or "priority". */
  target: string
  label: string
  before: string
  after: string
  text: string
  evidence: Evidence[]
  status: AvisoStatus
}

export type CartaOrigin = 'llamante' | 'sistema' | 'operador'

/** One line of the Carta. `key` is stable across versions: ampliaciones diff by it. */
export interface CartaDato {
  key: string
  label: string
  value: string
  origin: CartaOrigin
  /** The llamante's phrase, when the dato was said. */
  quote: string | null
  /** False for a pre-marca: said by the llamante, not yet confirmed by the operador. */
  confirmed: boolean
}

/** Carta de Llamada: a template over confirmed data only. It carries no recursos. */
export interface Carta {
  where: CartaDato[]
  what: CartaDato[]
  priority: CartaDato[]
  at_risk: CartaDato[]
  instructions: CartaDato[]
  notes: CartaDato[]
  missing: { text: string; skipped: boolean }[]
}

export interface CartaChange {
  key: string
  label: string
  before: string | null
  after: string | null
}

/** A dato confirmed after derivar, added to the Carta already derivada. */
export interface Ampliacion {
  at: string
  action: string
  changes: CartaChange[]
}

export interface DerivedCarta {
  call_id: string
  line: Line
  derived_at: string
  carta: Carta
  ampliaciones: Ampliacion[]
}

/** One line of a traza told in natural language; `alert` when something went wrong. */
export interface TraceLine {
  text: string
  alert: boolean
}

export type IAStatus = 'ok' | 'repaired' | 'retried' | 'invalid' | 'timeout' | 'error'

/** One answer of the Lector con IA, as it came, and why it was not valid. */
export interface IAAttempt {
  raw: string
  error: string | null
  repaired: boolean
}

/** The traza of one lectura (detalle técnico): told in lines, plus the raw steps. */
export interface ReadingDetail {
  title: string
  lines: TraceLine[]
  trace: {
    index: number
    mode: CallState['mode']
    steps: { step: 'relato' | 'reglas' | 'ia' | 'combinacion'; ms: number }[]
    /** Null in modo simulado: the Lector con IA did not run. */
    ia: { status: IAStatus; attempts: IAAttempt[] } | null
  }
}

export type ActionKind =
  | 'confirm_location'
  | 'correct_location'
  | 'confirm_type'
  | 'choose_type'
  | 'set_priority'
  | 'confirm_premark'
  | 'answer_question'
  | 'skip_question'
  | 'mark_instruction_read'
  | 'resolve_contradiction'
  | 'add_note'

export interface Action {
  kind: ActionKind
  target?: string
  value?: string
  reason?: string
}

async function request<T>(path: string, body?: unknown, empty = false): Promise<T> {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res
      .json()
      .then((j: { detail?: unknown }) => (typeof j.detail === 'string' ? j.detail : ''))
      .catch(() => '')
    throw new Error(detail || `${path} → HTTP ${res.status}`)
  }
  return (empty ? undefined : await res.json()) as T
}

export const api = {
  health: () => request<Health>('/api/health'),
  catalog: () => request<Catalog>('/api/catalog'),
  samples: () => request<SampleCall[]>('/api/samples'),
  sample: (id: string) => request<SampleCall>(`/api/samples/${encodeURIComponent(id)}`),
  parseTranscript: (text: string) => request<ParsedTurn[]>('/api/transcripts/parse', { text }),
  openCall: (line: Line, sampleId?: string) =>
    request<CallState>('/api/calls', { line, sample_id: sampleId ?? null }),
  addTurn: (callId: string, turn: ParsedTurn) =>
    request<CallState>(`/api/calls/${callId}/turns`, { speaker: turn.speaker, text: turn.text }),
  act: (callId: string, action: Action) =>
    request<CallState>(`/api/calls/${callId}/actions`, action),
  derive: (callId: string) => request<CallState>(`/api/calls/${callId}/derive`, {}),
  close: (callId: string) => request<void>(`/api/calls/${callId}/close`, {}, true),
  readings: (callId: string) => request<ReadingDetail[]>(`/api/calls/${callId}/readings`),
  dispatch: () => request<DerivedCarta[]>('/api/dispatch'),
}
