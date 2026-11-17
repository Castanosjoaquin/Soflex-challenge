import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Action, type CallState, type Health, type ParsedTurn, type SampleCall } from './api'
import { LocationCard } from './components/LocationCard'
import { Relato } from './components/Relato'
import { StageBar } from './components/StageBar'

/** Pause before a turno: its own delay_ms if it has one, else roughly the time to say it. */
function delayFor(turn: ParsedTurn, isFirst: boolean): number {
  if (turn.delay_ms !== undefined) return turn.delay_ms
  if (isFirst) return 600
  return Math.min(1000 + turn.text.length * 15, 5000)
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [samples, setSamples] = useState<SampleCall[]>([])
  const [sample, setSample] = useState<SampleCall | null>(null)
  const [call, setCall] = useState<CallState | null>(null)
  const [cursor, setCursor] = useState(0)
  const [paused, setPaused] = useState(false)
  const [speed, setSpeed] = useState<1 | 2>(1)
  const [busy, setBusy] = useState(false)
  const [focused, setFocused] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Bumped on every new llamada so responses from a replaced one are ignored.
  const generation = useRef(0)

  useEffect(() => {
    Promise.all([api.health(), api.samples()])
      .then(([h, s]) => {
        setHealth(h)
        setSamples(s)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))

  const start = async (picked: SampleCall) => {
    const gen = ++generation.current
    setSample(picked)
    setCall(null)
    setCursor(0)
    setPaused(false)
    setError(null)
    try {
      const opened = await api.openCall(picked.line, picked.id)
      if (gen === generation.current) setCall(opened)
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

  // Live replay: one POST per turno, after its pause.
  useEffect(() => {
    if (!sample || !call || paused || busy || cursor >= sample.turns.length) return
    const timer = setTimeout(() => void step(), delayFor(sample.turns[cursor], cursor === 0) / speed)
    return () => clearTimeout(timer)
  }, [sample, call, paused, busy, cursor, speed, step])

  const finished = sample !== null && cursor >= sample.turns.length
  const canConfirm = call?.location != null && call.location.confidence !== 'confirmado'

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.metaKey || e.ctrlKey || e.altKey) return
      const key = e.key.toLowerCase()
      if (key === ' ') {
        e.preventDefault()
        setPaused((p) => !p)
      } else if (key === 'n') void step()
      else if (key === 'x') setSpeed((s) => (s === 1 ? 2 : 1))
      else if (key === 'c' && canConfirm && !busy) void act({ kind: 'confirm_location' })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div className="shell">
      <header className="topbar">
        <h1>Copiloto de Sala</h1>
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
          <h2>Llamadas de prueba</h2>
          <ul>
            {samples.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={sample?.id === s.id ? 'active' : ''}
                  onClick={() => void start(s)}
                >
                  <span className={`prio prio-${s.priority}`}>{s.priority}</span>
                  <span className="sample-id">{s.id.slice(-3)}</span>
                  {s.subcategory}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {call && sample ? (
          <section className="workspace">
            <StageBar stages={call.stages} />

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
            </div>

            <div className="columns">
              <section className="card">
                <h2>Relato</h2>
                <Relato
                  turns={call.turns}
                  evidence={call.location?.evidence ?? []}
                  focused={focused}
                  waiting={!finished && !paused}
                />
              </section>
              <LocationCard
                location={call.location}
                busy={busy}
                onConfirm={() => void act({ kind: 'confirm_location' })}
                onCorrect={(value) => void act({ kind: 'correct_location', value })}
                onFocus={setFocused}
              />
            </div>
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
