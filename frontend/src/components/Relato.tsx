import { useEffect, useRef } from 'react'
import type { Evidence, Turn } from '../api'

interface Props {
  turns: Turn[]
  /** Every phrase that backs a dato: shown marked. */
  evidence: Evidence[]
  /** The phrases of the dato the operador is looking at: shown lit. */
  focus: Evidence[]
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

function isLit(turnIndex: number, start: number, end: number, focus: Evidence[]): boolean {
  return focus.some((f) => f.turn_index === turnIndex && f.start < end && start < f.end)
}

export function Relato({ turns, evidence, focus, waiting }: Props) {
  // The list scrolls on its own, inside a card that stays in sight next to the datos.
  const list = useRef<HTMLOListElement>(null)

  // The newest turno goes on top: a new one brings the list back to the top to show it.
  useEffect(() => {
    const box = list.current
    if (box) box.scrollTop = 0
  }, [turns.length])

  // A dato under the pointer: bring its phrase into the relato's view, without moving the page.
  useEffect(() => {
    const box = list.current
    const mark = box?.querySelector<HTMLElement>('mark.focused')
    if (!box || !mark) return
    const top = mark.getBoundingClientRect().top - box.getBoundingClientRect().top
    if (top < 0 || top > box.clientHeight - mark.offsetHeight) {
      box.scrollTop += top - box.clientHeight / 3
    }
  }, [focus])

  if (turns.length === 0 && !waiting) {
    return <p className="muted">Todavía no hay turnos.</p>
  }
  return (
    <ol className="relato" ref={list}>
      {waiting && <li className="turn turn-waiting muted">…</li>}
      {[...turns].reverse().map((turn) => {
        let offset = 0
        return (
          <li key={turn.index} className={`turn turn-${turn.speaker}`}>
            <span className="speaker">{turn.speaker === 'operador' ? 'Operador' : 'Llamante'}</span>
            <p>
              {segments(
                turn.text,
                evidence.filter((e) => e.turn_index === turn.index),
              ).map((seg, i) => {
                const start = offset
                offset += seg.text.length
                return seg.mark ? (
                  <mark
                    key={i}
                    className={isLit(turn.index, start, offset, focus) ? 'focused' : undefined}
                  >
                    {seg.text}
                  </mark>
                ) : (
                  <span key={i}>{seg.text}</span>
                )
              })}
            </p>
          </li>
        )
      })}
    </ol>
  )
}
