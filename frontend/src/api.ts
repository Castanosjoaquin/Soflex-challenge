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
  delay_ms?: number
}

export interface SampleCall {
  id: string
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

export interface SignalValue {
  signal_id: string
  value: SignalAnswer
  evidence: Evidence | null
  source: Source
  confidence: Confidence
}

export interface Incident {
  category: string
  subtype: string | null
  evidence: Evidence[]
  confidence: Confidence
  source: Source
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
  signals: SignalValue[]
  priority: PriorityAssessment | null
  checklist: ChecklistItem[]
  skipped_questions: string[]
  next_question: NextQuestion | null
  /** `alert`: the llamada already needs what this etapa lacks (① without dirección). */
  stages: { id: StageId; status: StageStatus; alert: boolean }[]
}

export type ActionKind =
  | 'confirm_location'
  | 'correct_location'
  | 'confirm_type'
  | 'set_priority'
  | 'confirm_premark'
  | 'answer_question'
  | 'skip_question'

export interface Action {
  kind: ActionKind
  target?: string
  value?: string
  reason?: string
}

async function request<T>(path: string, body?: unknown): Promise<T> {
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
  return (await res.json()) as T
}

export const api = {
  health: () => request<Health>('/api/health'),
  catalog: () => request<Catalog>('/api/catalog'),
  samples: () => request<SampleCall[]>('/api/samples'),
  sample: (id: string) => request<SampleCall>(`/api/samples/${encodeURIComponent(id)}`),
  openCall: (line: Line, sampleId?: string) =>
    request<CallState>('/api/calls', { line, sample_id: sampleId ?? null }),
  addTurn: (callId: string, turn: ParsedTurn) =>
    request<CallState>(`/api/calls/${callId}/turns`, { speaker: turn.speaker, text: turn.text }),
  act: (callId: string, action: Action) =>
    request<CallState>(`/api/calls/${callId}/actions`, action),
}
