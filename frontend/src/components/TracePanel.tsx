import { useEffect, useRef, useState } from 'react'
import { api, type ReadingDetail } from '../api'
import { KEYS, keyLabel } from '../shortcuts'

interface Props {
  callId: string
  /** Lecturas so far (one per turno): a new one refetches the trazas while the panel is open. */
  lecturas: number
  /** Open or closed: R toggles it from the keyboard too. */
  open: boolean
  onToggle: (open: boolean) => void
}

/**
 * Detalle técnico (SPEC §5.11): the traza of each lectura, told in natural language, the newest
 * first. Hidden by default: it is for the equipo técnico, and it only asks the API while open.
 */
export function TracePanel({ callId, lecturas, open, onToggle }: Props) {
  const panel = useRef<HTMLDetailsElement>(null)
  // Kept with the llamada they belong to, so a new llamada never shows the trazas of the last.
  const [loaded, setLoaded] = useState<{ callId: string; readings: ReadingDetail[] } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let live = true
    api
      .readings(callId)
      .then((r) => {
        if (!live) return
        setLoaded({ callId, readings: r })
        setError(null)
      })
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      live = false
    }
  }, [open, callId, lecturas])

  // It opens at the bottom of the page: bring it into view.
  useEffect(() => {
    if (open) panel.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [open])

  const shown = loaded?.callId === callId ? [...loaded.readings].reverse() : []

  return (
    <details
      ref={panel}
      className="card trace-panel"
      open={open}
      onToggle={(e) => onToggle(e.currentTarget.open)}
    >
      <summary>
        Detalle técnico · {lecturas === 1 ? '1 lectura' : `${lecturas} lecturas`}{' '}
        <kbd>{keyLabel(KEYS.trace)}</kbd>
      </summary>
      {error && <p className="error">{error}</p>}
      {open && lecturas === 0 && (
        <p className="muted">Todavía no hubo lecturas en esta llamada.</p>
      )}
      <ol className="trace-list">
        {shown.map((r, i) => (
          <li key={r.trace.index}>
            <details open={i === 0}>
              <summary>{r.title}</summary>
              <ul className="trace-lines">
                {r.lines.map((line, j) => (
                  <li key={j} className={line.alert ? 'alert' : undefined}>
                    {line.text}
                  </li>
                ))}
              </ul>
              {r.trace.ia && r.trace.ia.attempts.length > 0 && (
                <details className="trace-raw">
                  <summary>
                    Respuestas de la IA tal como llegaron ({r.trace.ia.attempts.length})
                  </summary>
                  {r.trace.ia.attempts.map((a, j) => (
                    <div key={j}>
                      <span className={a.error ? 'muted alert' : 'muted'}>
                        Intento {j + 1}
                        {a.error ? ` · ${a.error}` : a.repaired ? ' · reparado' : ' · válido'}
                      </span>
                      <pre>{a.raw}</pre>
                    </div>
                  ))}
                </details>
              )}
            </details>
          </li>
        ))}
      </ol>
    </details>
  )
}
