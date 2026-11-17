import { useState } from 'react'
import type { Confidence, Evidence, Location } from '../api'
import { formatAddress } from '../format'
import { lit } from '../lit'
import { KEYS, keyLabel } from '../shortcuts'

const CONFIDENCE_TEXT: Record<Confidence, string> = {
  confirmado: 'Confirmado',
  probable: 'Probable',
  a_confirmar: 'A confirmar',
}

const fold = (text: string) =>
  text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/^(av\.?|avda\.?|avenida|calle)\s+/i, '')
    .replace(/[^\w ]/g, '')
    .trim()
    .toLowerCase()

/** The operador typed a street the matcher read as another official name ("Biyinghurst"). */
function typedDiffers(location: Location): boolean {
  return (
    location.source === 'operador' &&
    !!location.street &&
    !!location.street_official &&
    fold(location.street) !== fold(location.street_official)
  )
}

interface Props {
  location: Location | null
  busy: boolean
  /** The correction box is open (U opens it too). */
  editing: boolean
  onEdit: (editing: boolean) => void
  onConfirm: () => void
  onCorrect: (value: string) => void
  onFocus: (evidence: Evidence[]) => void
}

export function LocationCard({
  location,
  busy,
  editing,
  onEdit,
  onConfirm,
  onCorrect,
  onFocus,
}: Props) {
  const correct = editing ? (
    <CorrectForm
      initial={location ? formatAddress(location) : ''}
      busy={busy}
      onCancel={() => onEdit(false)}
      onSubmit={(value) => {
        onCorrect(value)
        onEdit(false)
      }}
    />
  ) : null

  if (!location) {
    return (
      <section className="card">
        <h2>① Ubicación</h2>
        <p className="muted">Esperando que el llamante diga dónde es.</p>
        {correct ?? (
          <div className="actions">
            <button type="button" className="secondary" onClick={() => onEdit(true)}>
              Cargar a mano <kbd>{keyLabel(KEYS.correctLocation)}</kbd>
            </button>
          </div>
        )}
      </section>
    )
  }

  const confirmed = location.confidence === 'confirmado'

  return (
    <section className="card location" {...lit(onFocus, location.evidence)}>
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
        {location.candidates.length > 1 && (
          <>
            <dt>¿Cuál?</dt>
            <dd className="candidates">{location.candidates.join(' · ')}</dd>
          </>
        )}
        {typedDiffers(location) && (
          <>
            <dt>Tipeaste</dt>
            <dd className="typed">
              “{location.street}” → <strong>{location.street_official}</strong>. Si no es esa
              calle, corregí de nuevo.
            </dd>
          </>
        )}
        {location.street && !location.street_official && (
          <>
            <dt />
            <dd className="muted">“{location.street}” no está en la lista oficial de calles.</dd>
          </>
        )}
      </dl>
      {correct ?? (
        <div className="actions">
          <button type="button" disabled={busy || confirmed} onClick={onConfirm}>
            Confirmar <kbd>{keyLabel(KEYS.confirmLocation)}</kbd>
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={() => onEdit(true)}>
            Corregir <kbd>{keyLabel(KEYS.correctLocation)}</kbd>
          </button>
        </div>
      )}
    </section>
  )
}

interface CorrectFormProps {
  initial: string
  busy: boolean
  onCancel: () => void
  onSubmit: (value: string) => void
}

/** The dirección as the operador types it; Enter saves, Esc leaves it as it was. */
function CorrectForm({ initial, busy, onCancel, onSubmit }: CorrectFormProps) {
  const [draft, setDraft] = useState(initial)
  return (
    <form
      className="correct"
      onSubmit={(e) => {
        e.preventDefault()
        if (draft.trim()) onSubmit(draft.trim())
        else onCancel()
      }}
    >
      <input
        autoFocus
        onFocus={(e) => e.target.select()}
        value={draft}
        aria-label="Dirección corregida"
        placeholder="Calle y altura, p. ej. Av. Corrientes 1540"
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
      />
      <button type="submit" disabled={busy}>
        Guardar
      </button>
    </form>
  )
}
