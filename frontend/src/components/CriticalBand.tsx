import type { InstructionItem } from '../api'

interface Props {
  instruction: InstructionItem | null
  busy: boolean
  onRead: () => void
}

/** The instrucción crítica, at once and in red, whatever the etapa (DESIGN §2, regla 3). */
export function CriticalBand({ instruction, busy, onRead }: Props) {
  if (!instruction) return null
  return (
    <div className={`critical-band${instruction.read ? ' critical-band-read' : ''}`} role="alert">
      <p>
        <small>Instrucción crítica · leer ya</small>
        {instruction.text}
      </p>
      {instruction.read ? (
        <span className="instruction-done">✔ leída</span>
      ) : (
        <button type="button" disabled={busy} onClick={onRead}>
          Leída <kbd>L</kbd>
        </button>
      )}
    </div>
  )
}
