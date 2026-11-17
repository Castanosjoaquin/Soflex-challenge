import { useState } from 'react'
import { KEYS, keyLabel } from '../shortcuts'

/** The nota box, which O focuses from the keyboard. */
export const NOTE_INPUT_ID = 'note-input'

interface Props {
  notes: string[]
  busy: boolean
  onAdd: (text: string) => void
}

/**
 * The operador's own notas: the only free-text box of the panel (DESIGN §6). Each one goes to
 * the Carta as written, and after derivar it reaches the despachador as an ampliación.
 */
export function NoteBox({ notes, busy, onAdd }: Props) {
  const [draft, setDraft] = useState('')
  return (
    <section className="card notes">
      <h2>
        Notas del operador <kbd>{keyLabel(KEYS.note)}</kbd>
      </h2>
      {notes.length > 0 && (
        <ol className="note-list">
          {notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ol>
      )}
      <form
        className="correct"
        onSubmit={(e) => {
          e.preventDefault()
          if (!draft.trim() || busy) return
          onAdd(draft.trim())
          setDraft('')
          // Back to the keys: the next action is rarely another nota.
          e.currentTarget.querySelector('input')?.blur()
        }}
      >
        <input
          id={NOTE_INPUT_ID}
          value={draft}
          maxLength={500}
          aria-label="Nota del operador"
          placeholder="Para el despachador"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && e.currentTarget.blur()}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          Agregar
        </button>
      </form>
    </section>
  )
}
