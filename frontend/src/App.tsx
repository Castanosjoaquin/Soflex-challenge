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
  type SampleCall,
  type SignalAnswer,
} from './api'
import { CartaPanel } from './components/CartaPanel'
import { Checklist } from './components/Checklist'
import { CriticalBand } from './components/CriticalBand'
import { IncidentCard } from './components/IncidentCard'
import { Instructions } from './components/Instructions'
import { LocationCard } from './components/LocationCard'
import { Relato } from './components/Relato'
import { StageBar } from './components/StageBar'
import { ANSWER_KEYS, answerTarget, skipTarget } from './questions'

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
    setError(null)
    try {
      const opened = await api.openCall(picked.line, picked.sampleId ?? undefined)
      if (gen === generation.current) setCall(opened)
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
  // Every phrase that backs a dato is marked in the relato.
  const evidence: Evidence[] = call
    ? [
        ...(call.location?.evidence ?? []),
        ...(call.incident?.evidence ?? []),
        ...call.signals.flatMap((s) => (s.evidence ? [s.evidence] : [])),
      ]
    : []

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing =
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLSelectElement ||
        e.target instanceof HTMLTextAreaElement
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return
      const key = e.key.toLowerCase()
      const answer = ANSWER_KEYS.find(([k]) => k === key)
      if (key === ' ') {
        e.preventDefault()
        setPaused((p) => !p)
      } else if (key === 'n') void step()
      else if (key === 'x') setSpeed((s) => (s === 1 ? 2 : 1))
      else if (key === 'c' && canConfirm && !busy) void act({ kind: 'confirm_location' })
      else if (key === 't' && canConfirmType && !busy) void act({ kind: 'confirm_type' })
      else if (key === 'v' && premark && !busy)
        void act({ kind: 'confirm_premark', target: premark.question_id })
      else if (key === 's' && !busy) skipNext()
      else if (key === 'l' && nextInstruction && !busy) markRead(nextInstruction.instruction_id)
      else if (key === 'd' && call?.can_derive && !call.derived && !busy) void derive()
      else if (answer && !busy) answerNext(answer[1])
      else if (key === 'p' && call?.priority) {
        e.preventDefault()
        setEditingPriority(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div className="shell">
      <header className="topbar">
        <h1>Copiloto de Sala</h1>
        <a className="badge" href="/despacho" target="_blank" rel="noreferrer">
          Bandeja del despachador ↗
        </a>
        {health && (
          <span className="badge" title="Lector activo">
            {health.provider === 'mock' ? 'Modo simulado' : 'IA'} · {health.catalog_size} llamadas de
            prueba
          </span>
        )}
      </header>

      {error && <p className="error">{error}</p>}

      <main className="layout">
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

        {call && sample ? (
          <section className="workspace">
            <StageBar
              stages={call.stages}
              nextQuestion={nextQuestion}
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

            <div className="playback" role="toolbar" aria-label="Reproducción">
              <span className="line">Línea {call.line}</span>
              <button type="button" onClick={() => setPaused((p) => !p)} disabled={finished}>
                {paused ? '▶ Seguir' : '❚❚ Pausa'} <kbd>Espacio</kbd>
              </button>
              <button type="button" onClick={() => void step()} disabled={finished || busy}>
                ⏭ Siguiente turno <kbd>N</kbd>
              </button>
              <button
                type="button"
                className={speed === 2 ? 'on' : ''}
                onClick={() => setSpeed((s) => (s === 1 ? 2 : 1))}
              >
                ×2 <kbd>X</kbd>
              </button>
              <span className="muted">
                Turno {cursor}/{sample.turns.length}
                {finished ? ' · fin del relato' : paused ? ' · en pausa' : ''}
              </span>
              <button type="button" className="secondary" onClick={() => void close()}>
                Cerrar llamada
              </button>
            </div>

            <div className="columns">
              <section className="card">
                <h2>Relato</h2>
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
                  onConfirm={() => void act({ kind: 'confirm_location' })}
                  onCorrect={(value) => void act({ kind: 'correct_location', value })}
                  onFocus={(on) => setFocus(on ? (call.location?.evidence ?? []) : [])}
                />
                <IncidentCard
                  incident={call.incident}
                  priority={call.priority}
                  catalog={catalog}
                  busy={busy}
                  editingPriority={editingPriority}
                  onEditPriority={setEditingPriority}
                  onConfirmType={(value) => void act({ kind: 'confirm_type', value })}
                  onSetPriority={(level, reason) =>
                    void act({ kind: 'set_priority', value: level, reason })
                  }
                  onFocus={setFocus}
                />
                <Checklist
                  items={call.checklist}
                  nextId={nextQuestion?.id ?? null}
                  busy={busy}
                  onConfirm={(target) => void act({ kind: 'confirm_premark', target })}
                  onAnswer={(target, value) => void act({ kind: 'answer_question', target, value })}
                  onFocus={setFocus}
                />
              </div>
              <Instructions
                items={call.instructions}
                nextId={nextInstruction?.instruction_id ?? null}
                busy={busy}
                onRead={markRead}
              />
            </div>

            <CartaPanel call={call} busy={busy} onDerive={() => void derive()} />
          </section>
        ) : (
          <section className="workspace card">
            <p className="muted">Elegí una llamada de prueba para reproducirla turno a turno.</p>
          </section>
        )}
      </main>
    </div>
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
