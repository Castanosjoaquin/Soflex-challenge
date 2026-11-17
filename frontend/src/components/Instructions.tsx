import type { InstructionItem } from '../api'

interface Props {
  items: InstructionItem[]
  /** The instrucción that the L key marks: the first one not read yet. */
  nextId: string | null
  busy: boolean
  onRead: (instructionId: string) => void
}

/** Etapa ⑤: the instrucciones to read aloud, numbered, the crítica first. */
export function Instructions({ items, nextId, busy, onRead }: Props) {
  return (
    <section className="card instructions">
      <h2>⑤ Instrucciones</h2>
      {items.length === 0 ? (
        <p className="muted">Aparecen cuando se sabe qué pasa. Salen del protocolo, nunca de la IA.</p>
      ) : (
        <>
          <ol className="instruction-list">
            {items.map((item) => (
              <li
                key={item.instruction_id}
                className={`instruction${item.critical ? ' instruction-critical' : ''}${item.read ? ' instruction-read' : ''}`}
              >
                <span className="instruction-text">{item.text}</span>
                {item.read ? (
                  <span className="instruction-done" title="Leída">
                    ✔ leída
                  </span>
                ) : (
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => onRead(item.instruction_id)}
                  >
                    Leída {item.instruction_id === nextId && <kbd>L</kbd>}
                  </button>
                )}
              </li>
            ))}
          </ol>
          <p className="muted legend">Para leer en voz alta, en este orden.</p>
        </>
      )}
    </section>
  )
}
