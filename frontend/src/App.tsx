import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  type Action,
  type CallState,
  type Catalog,
  type Evidence,
  type Health,
  type Line,
  type ParsedTurn,
  type Resolution,
  type SampleCall,
  type SignalAlternative,
  type SignalAnswer,
} from './api'
import { AvisoBand } from './components/AvisoBand'
import { CartaPanel } from './components/CartaPanel'
import { Checklist } from './components/Checklist'
import { CriticalBand } from './components/CriticalBand'
import { IncidentCard, TYPE_PICKER_ID } from './components/IncidentCard'
import { Instructions } from './components/Instructions'
import { LocationCard } from './components/LocationCard'
import { NOTE_INPUT_ID, NoteBox } from './components/NoteBox'
import { Relato } from './components/Relato'
import { ShortcutHelp } from './components/ShortcutHelp'
import { StageBar } from './components/StageBar'
import { TracePanel } from './components/TracePanel'
import { answerTarget, skipTarget } from './questions'
import { ANSWER_KEYS, DISPUTE_KEYS, KEYS, keyLabel } from './shortcuts'

type Mode = CallState['mode']

const MODE_TEXT: Record<Mode, string> = {
  simulado: 'Modo simulado',
  ia: 'IA',
  reglas: 'Modo reglas',
}

const MODE_TITLE: Record<Mode, string> = {
  simulado: 'Sin IA configurada: lee solo el lector por reglas',
  ia: 'Leen el lector por reglas y el lector con IA',
  reglas: 'La IA no respondió a tiempo o respondió mal: esta lectura es solo por reglas',
}

/** Pause before a turno: its own delay_ms if it has one, else roughly the time to say it. */
function delayFor(turn: ParsedTurn, isFirst: boolean): number {
  if (turn.delay_ms != null) return turn.delay_ms
  if (isFirst) return 600
  return Math.min(1000 + turn.text.length * 15, 5000)
}

const LINES: Line[] = ['911', '107', '103', '147', 'app']

/** A llamada to replay: a llamada de prueba from the API, or a text the operador pasted. */
type Replay = Pick<SampleCall, 'id' | 'line' | 'turns'> & {
  sampleId: string | null
}

const fromSample = (s: SampleCall): Replay => ({ ...s, sampleId: s.id })

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [samples, setSamples] = useState<SampleCall[]>([])
  const [sample, setSample] = useState<Replay | null>(null)
  const [pasted, setPasted] = useState('')
  const [pastedLine, setPastedLine] = useState<Line>('911')
  const [call, setCall] = useState<CallState | null>(null)
  const [cursor, setCursor] = useState(0)
  const [paused, setPaused] = useState(false)
  const [speed, setSpeed] = useState<1 | 2>(1)
  const [busy, setBusy] = useState(false)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  // The phrases of the dato under the pointer, lit in the relato.
  const [focus, setFocus] = useState<Evidence[]>([])
  const [editingPriority, setEditingPriority] = useState(false)
  const [editingLocation, setEditingLocation] = useState(false)
  const [traceOpen, setTraceOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  // The list of llamadas de prueba folds away during a llamada, to give the panel the width.
  const [samplesOpen, setSamplesOpen] = useState(false)
  const [openedAt, setOpenedAt] = useState(0)
  const [error, setError] = useState<string | null>(null)
  // Bumped on every new llamada so responses from a replaced one are ignored.
  const generation = useRef(0)

  useEffect(() => {
    Promise.all([api.health(), api.samples(), api.catalog()])
      .then(([h, s, c]) => {
        setHealth(h)
        setSamples(s)
        setCatalog(c)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))

  const start = async (picked: Replay) => {
    const gen = ++generation.current
    setSample(picked)
    setCall(null)
    setCursor(0)
    setPaused(false)
    setFocus([])
    setEditingPriority(false)
    setEditingLocation(false)
    setTraceOpen(false)
    setSamplesOpen(false)
    setError(null)
    try {
      const opened = await api.openCall(picked.line, picked.sampleId ?? undefined)
      if (gen !== generation.current) return
      setCall(opened)
      setOpenedAt(Date.now())
    } catch (e) {
      fail(e)
    }
  }

  const playPasted = async () => {
    try {
      const turns = await api.parseTranscript(pasted)
      if (turns.length === 0) return setError('El texto pegado está vacío.')
      await start({ id: 'pegado', line: pastedLine, turns, sampleId: null })
    } catch (e) {
      fail(e)
    }
  }

  const step = useCallback(async () => {
    if (!sample || !call || busy || cursor >= sample.turns.length) return
    const gen = generation.current
    setBusy(true)
    try {
      const next = await api.addTurn(call.call_id, sample.turns[cursor])
      if (gen !== generation.current) return
      setCall(next)
      setCursor((c) => c + 1)
    } catch (e) {
      fail(e)
      setPaused(true)
    } finally {
      if (gen === generation.current) setBusy(false)
    }
  }, [sample, call, busy, cursor])

  const act = async (action: Action) => {
    if (!call) return
    const gen = generation.current
    setBusy(true)
    try {
      const next = await api.act(call.call_id, action)
      if (gen === generation.current) setCall(next)
    } catch (e) {
      fail(e)
    } finally {
      if (gen === generation.current) setBusy(false)
    }
  }

  const derive = async () => {
    if (!call || !call.can_derive || call.derived) return
    const gen = generation.current
    setBusy(true)
    try {
      const next = await api.derive(call.call_id)
      if (gen === generation.current) setCall(next)
    } catch (e) {
      fail(e)
    } finally {
      if (gen === generation.current) setBusy(false)
    }
  }

  const close = async () => {
    if (!call) return
    const gen = ++generation.current
    try {
      await api.close(call.call_id)
    } catch (e) {
      fail(e)
    }
    if (gen !== generation.current) return
    setCall(null)
    setSample(null)
    setBusy(false)
  }

  // Live replay: one POST per turno, after its pause.
  useEffect(() => {
    if (!sample || !call || paused || busy || cursor >= sample.turns.length) return
    const timer = setTimeout(() => void step(), delayFor(sample.turns[cursor], cursor === 0) / speed)
    return () => clearTimeout(timer)
  }, [sample, call, paused, busy, cursor, speed, step])

  const finished = sample !== null && cursor >= sample.turns.length
  const canConfirm = call?.location != null && call.location.confidence !== 'confirmado'
  const canConfirmType = call?.incident != null && call.incident.confidence !== 'confirmado'
  const nextQuestion = call?.next_question ?? null
  const premark = call?.checklist.find((i) => i.status === 'pre_marcada') ?? null
  const answerNext = (value: SignalAnswer) => {
    const target = answerTarget(nextQuestion)
    if (target) void act({ kind: 'answer_question', target, value })
  }
  const skipNext = () => {
    const target = skipTarget(nextQuestion)
    if (target) void act({ kind: 'skip_question', target })
  }
  // L marks the first instrucción not read yet: the crítica, when there is one, comes first.
  const nextInstruction = call?.instructions.find((i) => !i.read) ?? null
  const markRead = (instructionId: string) =>
    void act({ kind: 'mark_instruction_read', target: instructionId })
  // A and M resolve the first aviso still pending, the one the band shows.
  const aviso = call?.avisos.find((a) => a.status === 'pendiente') ?? null
  const resolve = (avisoId: string, resolution: Resolution) =>
    void act({ kind: 'resolve_contradiction', target: avisoId, value: resolution })
  // Every phrase that backs a dato is marked in the relato, and so is what a pending aviso heard.
  const evidence: Evidence[] = call
    ? [
        ...(aviso?.evidence ?? []),
        ...(call.location?.evidence ?? []),
        ...(call.incident?.evidence ?? []),
        ...call.signals.flatMap((s) => (s.evidence ? [s.evidence] : [])),
        ...call.signals.flatMap((s) => (s.alternative ? [s.alternative.evidence] : [])),
      ]
    : []
  const alternatives: Record<string, SignalAlternative> = Object.fromEntries(
    (call?.signals ?? []).flatMap((s) => (s.alternative ? [[s.signal_id, s.alternative]] : [])),
  )

  const disputeOptions = call?.type_dispute?.options ?? []
  const openTypePicker = () => {
    const picker = document.getElementById(TYPE_PICKER_ID)
    if (!(picker instanceof HTMLSelectElement)) return
    picker.focus()
    try {
      picker.showPicker()
    } catch {
      // Without showPicker the list stays focused: the arrows move through it.
    }
  }
  const askClose = () => {
    if (window.confirm('¿Cerrar la llamada? Sale de memoria; el registro y la bandeja quedan.'))
      void close()
  }

  useEffect(() => {
    // What each key does now; null when its action does not apply. Actions that go to the
    // server also wait for the one in flight.
    const free = !busy
    const shortcuts: Record<string, (() => void) | null> = {
      [KEYS.nextTurn]: call ? () => void step() : null,
      [KEYS.speed]: call ? () => setSpeed((s) => (s === 1 ? 2 : 1)) : null,
      [KEYS.confirmLocation]:
        canConfirm && free ? () => void act({ kind: 'confirm_location' }) : null,
      [KEYS.correctLocation]: call ? () => setEditingLocation(true) : null,
      [KEYS.confirmType]: canConfirmType && free ? () => void act({ kind: 'confirm_type' }) : null,
      [KEYS.otherType]: call?.incident && free ? openTypePicker : null,
      [KEYS.priority]: call?.priority ? () => setEditingPriority(true) : null,
      [KEYS.skip]: skipTarget(nextQuestion) && free ? skipNext : null,
      [KEYS.premark]:
        premark && free
          ? () => void act({ kind: 'confirm_premark', target: premark.question_id })
          : null,
      [KEYS.read]:
        nextInstruction && free ? () => markRead(nextInstruction.instruction_id) : null,
      [KEYS.avisoAccept]: aviso && free ? () => resolve(aviso.id, 'aceptar') : null,
      [KEYS.avisoKeep]: aviso && free ? () => resolve(aviso.id, 'mantener') : null,
      [KEYS.derive]: call?.can_derive && !call.derived && free ? () => void derive() : null,
      [KEYS.note]: call ? () => document.getElementById(NOTE_INPUT_ID)?.focus() : null,
      [KEYS.trace]: call ? () => setTraceOpen((o) => !o) : null,
      [KEYS.close]: call ? askClose : null,
    }
    DISPUTE_KEYS.forEach((key, i) => {
      const option = disputeOptions[i]
      shortcuts[key] =
        option && free ? () => void act({ kind: 'choose_type', value: option.category }) : null
    })
    for (const [key, value] of ANSWER_KEYS) {
      shortcuts[key] = answerTarget(nextQuestion) && free ? () => answerNext(value) : null
    }

    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const target = e.target instanceof HTMLElement ? e.target : null
      const typing = !!target?.closest('input, select, textarea, [contenteditable="true"]')
      if (e.key === 'Escape') {
        // Out of a box and back to the keys; each box also cancels its own edit on Esc.
        if (typing) target?.blur()
        else setHelpOpen(false)
        return
      }
      if (typing) return
      if (e.key === KEYS.help) return setHelpOpen((o) => !o)
      if (e.key === KEYS.pause) {
        // Space still presses the button, or opens the detalle técnico, reached with Tab.
        const pressable = target?.matches('button, summary, a, [role="radio"]')
        if (pressable && target?.matches(':focus-visible')) return
        e.preventDefault()
        if (call) setPaused((p) => !p)
        return
      }
      const run = shortcuts[e.key.toLowerCase()]
      if (!run) return
      // The key is not typed into the box it opens (U, P, O).
      e.preventDefault()
      run()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // The llamada's mode follows its last lectura; before one, what the server is configured for.
  const mode: Mode = call?.mode ?? (health?.provider === 'openai_compat' ? 'ia' : 'simulado')

  const showSamples = !call || samplesOpen

  return (
    <div className="shell">
      <header className="topbar">
        <h1>Copiloto de Sala</h1>
        {call && (
          <div className="call-meta" aria-label="Llamada en curso">
            <span title={`Llamada ${call.call_id}`}>
              Llamada <strong>{call.call_id.slice(0, 6).toUpperCase()}</strong>
            </span>
            <span>
              Línea <strong>{call.line}</strong>
            </span>
            <Elapsed since={openedAt} />
            <button type="button" className="secondary" onClick={() => void close()}>
              Cerrar llamada <kbd>{keyLabel(KEYS.close)}</kbd>
            </button>
          </div>
        )}
        <div className="topbar-tools">
          {health && (
            <span
              className={`badge mode-${mode}`}
              title={`${MODE_TITLE[mode]} · ${health.catalog_size} llamadas de prueba`}
            >
              {MODE_TEXT[mode]}
            </span>
          )}
          {call && (
            <button
              type="button"
              className={`secondary${samplesOpen ? ' on' : ''}`}
              aria-expanded={samplesOpen}
              onClick={() => setSamplesOpen((o) => !o)}
            >
              Llamadas de prueba
            </button>
          )}
          <a className="badge" href="/despacho" target="_blank" rel="noreferrer">
            Bandeja del despachador ↗
          </a>
          <button
            type="button"
            className={`secondary${helpOpen ? ' on' : ''}`}
            aria-expanded={helpOpen}
            onClick={() => setHelpOpen((o) => !o)}
          >
            Atajos <kbd>{keyLabel(KEYS.help)}</kbd>
          </button>
        </div>
      </header>

      {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}

      {error && <p className="error">{error}</p>}

      <main className={`layout${showSamples ? '' : ' layout-wide'}`}>
        {showSamples && (
          <aside className="samples">
            <h2>Llamadas demo</h2>
            <SampleList
              samples={samples.filter((s) => s.kind === 'demo')}
              activeId={sample?.id ?? null}
              onPick={(s) => void start(fromSample(s))}
            />

            <h2>Pegar un relato</h2>
            <form
              className="paste"
              onSubmit={(e) => {
                e.preventDefault()
                void playPasted()
              }}
            >
              <textarea
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
                rows={5}
                placeholder={
                  'Operador: 911, ¿su emergencia?\nLlamante: …\n\nSin prefijos, es un solo turno del llamante.'
                }
                aria-label="Texto de la llamada"
              />
              <div className="paste-actions">
                <select
                  value={pastedLine}
                  onChange={(e) => setPastedLine(e.target.value as Line)}
                  aria-label="Línea"
                >
                  {LINES.map((l) => (
                    <option key={l} value={l}>
                      Línea {l}
                    </option>
                  ))}
                </select>
                <button
                  type="submit"
                  className={sample?.id === 'pegado' ? 'active' : ''}
                  disabled={!pasted.trim()}
                >
                  ▶ Reproducir
                </button>
              </div>
            </form>

            <h2>Dataset</h2>
            <SampleList
              samples={samples.filter((s) => s.kind === 'dataset')}
              activeId={sample?.id ?? null}
              onPick={(s) => void start(fromSample(s))}
            />
          </aside>
        )}

        {call && sample ? (
          <section className="workspace">
            <StageBar
              stages={call.stages}
              nextQuestion={nextQuestion}
              canDerive={call.can_derive && !call.derived}
              busy={busy}
              onAnswer={answerNext}
              onSkip={skipNext}
            />

            <CriticalBand
              instruction={call.critical_instruction}
              busy={busy}
              onRead={() =>
                call.critical_instruction && markRead(call.critical_instruction.instruction_id)
              }
            />

            <AvisoBand avisos={call.avisos} busy={busy} onResolve={resolve} onFocus={setFocus} />

            <div className="columns">
              <section className="card relato-card">
                <header className="card-head">
                  <h2>Relato</h2>
                  <div className="playback" role="toolbar" aria-label="Reproducción">
                    <span className="muted">
                      Turno {cursor}/{sample.turns.length}
                      {finished ? ' · fin' : paused ? ' · en pausa' : ''}
                    </span>
                    <button
                      type="button"
                      onClick={() => setPaused((p) => !p)}
                      disabled={finished}
                      title={paused ? 'Seguir' : 'Pausa'}
                    >
                      {paused ? '▶' : '❚❚'} <kbd>{keyLabel(KEYS.pause)}</kbd>
                    </button>
                    <button
                      type="button"
                      onClick={() => void step()}
                      disabled={finished || busy}
                      title="Siguiente turno"
                    >
                      ⏭ <kbd>{keyLabel(KEYS.nextTurn)}</kbd>
                    </button>
                    <button
                      type="button"
                      className={speed === 2 ? 'on' : ''}
                      onClick={() => setSpeed((s) => (s === 1 ? 2 : 1))}
                      title="Velocidad ×2"
                    >
                      ×2 <kbd>{keyLabel(KEYS.speed)}</kbd>
                    </button>
                  </div>
                </header>
                <Relato
                  turns={call.turns}
                  evidence={evidence}
                  focus={focus}
                  waiting={!finished && !paused}
                />
              </section>
              <div className="stack">
                <LocationCard
                  location={call.location}
                  busy={busy}
                  editing={editingLocation}
                  onEdit={setEditingLocation}
                  onConfirm={() => void act({ kind: 'confirm_location' })}
                  onCorrect={(value) => void act({ kind: 'correct_location', value })}
                  onFocus={setFocus}
                />
                <IncidentCard
                  incident={call.incident}
                  dispute={call.type_dispute}
                  priority={call.priority}
                  catalog={catalog}
                  busy={busy}
                  editingPriority={editingPriority}
                  onEditPriority={setEditingPriority}
                  onConfirmType={(value) => void act({ kind: 'confirm_type', value })}
                  onChooseType={(value) => void act({ kind: 'choose_type', value })}
                  onSetPriority={(level, reason) =>
                    void act({ kind: 'set_priority', value: level, reason })
                  }
                  onFocus={setFocus}
                />
                <Checklist
                  items={call.checklist}
                  nextId={nextQuestion?.id ?? null}
                  alternatives={alternatives}
                  busy={busy}
                  onConfirm={(target) => void act({ kind: 'confirm_premark', target })}
                  onAnswer={(target, value) => void act({ kind: 'answer_question', target, value })}
                  onFocus={setFocus}
                />
              </div>
              <div className="stack side">
                <Instructions
                  items={call.instructions}
                  nextId={nextInstruction?.instruction_id ?? null}
                  busy={busy}
                  onRead={markRead}
                />
                <NoteBox
                  notes={call.notes}
                  busy={busy}
                  onAdd={(text) => void act({ kind: 'add_note', value: text })}
                />
              </div>
            </div>

            <CartaPanel call={call} busy={busy} onDerive={() => void derive()} onFocus={setFocus} />

            <TracePanel
              callId={call.call_id}
              lecturas={call.turns.length}
              open={traceOpen}
              onToggle={setTraceOpen}
            />
          </section>
        ) : (
          <section className="workspace card">
            <p className="muted">
              Elegí una llamada de prueba para reproducirla turno a turno, con el mouse o con Tab y
              Enter. Con <kbd>{keyLabel(KEYS.help)}</kbd> ves todos los atajos.
            </p>
          </section>
        )}
      </main>
    </div>
  )
}

/** Time since the llamada was opened, ticking every second. */
function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  const seconds = Math.max(0, Math.floor((now - since) / 1000))
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  return (
    <span title="Tiempo desde que se abrió la llamada">
      ⏱ <strong>{`${mm}:${ss}`}</strong>
    </span>
  )
}

function SampleList({
  samples,
  activeId,
  onPick,
}: {
  samples: SampleCall[]
  activeId: string | null
  onPick: (sample: SampleCall) => void
}) {
  return (
    <ul>
      {samples.map((s) => (
        <li key={s.id}>
          <button
            type="button"
            className={activeId === s.id ? 'active' : ''}
            onClick={() => onPick(s)}
            title={s.kind === 'demo' ? s.subcategory : undefined}
          >
            <span className={`prio prio-${s.priority}`}>{s.priority}</span>
            <span className="sample-id">{s.kind === 'demo' ? 'demo' : s.id.slice(-3)}</span>
            {s.title}
          </button>
        </li>
      ))}
    </ul>
  )
}
