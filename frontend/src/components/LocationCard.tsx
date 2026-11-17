import { useState } from 'react'
import type { Confidence, Location } from '../api'
import { formatAddress } from '../format'

const CONFIDENCE_TEXT: Record<Confidence, string> = {
  confirmado: 'Confirmado',
  probable: 'Probable',
  a_confirmar: 'A confirmar',
}

interface Props {
  location: Location | null
  busy: boolean
  onConfirm: () => void
  onCorrect: (value: string) => void
  onFocus: (focused: boolean) => void
}

export function LocationCard({ location, busy, onConfirm, onCorrect, onFocus }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  if (!location) {
    return (
      <section className="card">
        <h2>① Ubicación</h2>
        <p className="muted">Esperando que el llamante diga dónde es.</p>
      </section>
    )
  }

  const confirmed = location.confidence === 'confirmado'
  const submit = () => {
    if (draft.trim()) onCorrect(draft.trim())
    setEditing(false)
  }

  return (
    <section
      className="card location"
      onMouseEnter={() => onFocus(true)}
      onMouseLeave={() => onFocus(false)}
    >
      <header className="card-head">
        <h2>① Ubicación</h2>
        <span className={`confidence confidence-${location.confidence}`}>
          {CONFIDENCE_TEXT[location.confidence]}
          {location.source === 'operador' ? ' · corregida' : ''}
        </span>
      </header>
      <dl className="two-lines">
        <dt>Dijo</dt>
        <dd className="said">“{location.said || '—'}”</dd>
        <dt>Dirección</dt>
        <dd className="address">{formatAddress(location)}</dd>
      </dl>
      {editing ? (
        <form
          className="correct"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <input
            autoFocus
            onFocus={(e) => e.target.select()}
            value={draft}
            placeholder="Calle y altura, p. ej. Av. Corrientes 1540"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && setEditing(false)}
          />
          <button type="submit" disabled={busy}>
            Guardar
          </button>
        </form>
      ) : (
        <div className="actions">
          <button type="button" disabled={busy || confirmed} onClick={onConfirm}>
            Confirmar <kbd>C</kbd>
          </button>
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={() => {
              setDraft(formatAddress(location))
              setEditing(true)
            }}
          >
            Corregir
          </button>
        </div>
      )}
    </section>
  )
}
