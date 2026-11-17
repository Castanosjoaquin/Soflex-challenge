import type { Evidence, Turn } from '../api'

interface Props {
  turns: Turn[]
  evidence: Evidence[]
  /** Emphasize the evidence while the operador looks at the dato it backs. */
  focused: boolean
  waiting: boolean
}

function segments(text: string, ranges: Evidence[]): { text: string; mark: boolean }[] {
  const sorted = [...ranges].sort((a, b) => a.start - b.start)
  const out: { text: string; mark: boolean }[] = []
  let cursor = 0
  for (const r of sorted) {
    const start = Math.max(r.start, cursor)
    if (r.end <= start) continue
    if (start > cursor) out.push({ text: text.slice(cursor, start), mark: false })
    out.push({ text: text.slice(start, r.end), mark: true })
    cursor = r.end
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor), mark: false })
  return out
}

export function Relato({ turns, evidence, focused, waiting }: Props) {
  if (turns.length === 0 && !waiting) {
    return <p className="muted">Todavía no hay turnos.</p>
  }
  return (
    <ol className="relato">
      {turns.map((turn) => (
        <li key={turn.index} className={`turn turn-${turn.speaker}`}>
          <span className="speaker">{turn.speaker === 'operador' ? 'Operador' : 'Llamante'}</span>
          <p>
            {segments(
              turn.text,
              evidence.filter((e) => e.turn_index === turn.index),
            ).map((seg, i) =>
              seg.mark ? (
                <mark key={i} className={focused ? 'focused' : undefined}>
                  {seg.text}
                </mark>
              ) : (
                <span key={i}>{seg.text}</span>
              ),
            )}
          </p>
        </li>
      ))}
      {waiting && <li className="turn turn-waiting muted">…</li>}
    </ol>
  )
}
