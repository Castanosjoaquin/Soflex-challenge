import { useState } from 'react'
import type {
  Catalog,
  Confidence,
  Evidence,
  Incident,
  Priority,
  PriorityAssessment,
  Source,
  TypeDispute,
} from '../api'
import { DISPUTE_KEYS } from '../questions'

const CONFIDENCE_TEXT: Record<Confidence, string> = {
  confirmado: 'Confirmado',
  probable: 'Probable',
  a_confirmar: 'A confirmar',
}

const LEVELS: Priority[] = ['P1', 'P2', 'P3', 'P4']

const SOURCE_TEXT: Record<Source, string> = { reglas: 'reglas', ia: 'IA', operador: 'operador' }

interface Props {
  incident: Incident | null
  dispute: TypeDispute | null
  priority: PriorityAssessment | null
  catalog: Catalog | null
  busy: boolean
  editingPriority: boolean
  onEditPriority: (editing: boolean) => void
  onConfirmType: (value?: string) => void
  onChooseType: (category: string) => void
  onSetPriority: (level: Priority, reason: string) => void
  onFocus: (evidence: Evidence[]) => void
}

type Named = { id: string; label: string }

function labelOf(list: Named[] | undefined, id: string | null): string {
  if (!id) return '—'
  return list?.find((x) => x.id === id)?.label ?? id
}

/** ② ¿Qué pasa?: tipo, subtipo, prioridad and its porqué, each lighting its phrase on hover. */
export function IncidentCard({
  incident,
  dispute,
  priority,
  catalog,
  busy,
  editingPriority,
  onEditPriority,
  onConfirmType,
  onChooseType,
  onSetPriority,
  onFocus,
}: Props) {
  const lit = (evidence: Evidence[]) => ({
    onMouseEnter: () => onFocus(evidence),
    onMouseLeave: () => onFocus([]),
  })

  if (!incident && !priority) {
    return (
      <section className="card">
        <h2>② ¿Qué pasa?</h2>
        <p className="muted">Esperando que el relato diga qué pasa.</p>
      </section>
    )
  }

  const confirmed = incident?.confidence === 'confirmado'

  return (
    <section className="card incident">
      <header className="card-head">
        <h2>② ¿Qué pasa?</h2>
        {incident && (
          <span className={`confidence confidence-${incident.confidence}`}>
            {CONFIDENCE_TEXT[incident.confidence]}
            {incident.source === 'operador' ? ' · elegido' : ''}
          </span>
        )}
      </header>

      {dispute && (
        <div className="dispute" role="group" aria-label="Tipo en disputa">
          <p>
            <strong>
              ¿{dispute.options.map((o) => labelOf(catalog?.types, o.category)).join(' o ')}?
            </strong>{' '}
            <span className="muted">Los lectores no coinciden; mientras, rige la más urgente.</span>
          </p>
          <div className="actions">
            {dispute.options.map((o, i) => (
              <button
                key={o.category}
                type="button"
                className={o.category === incident?.category ? '' : 'secondary'}
                disabled={busy}
                onClick={() => onChooseType(o.category)}
                {...lit(o.evidence)}
              >
                {labelOf(catalog?.types, o.category)}
                {o.subtype ? ` · ${labelOf(catalog?.subtypes, o.subtype)}` : ''}
                <span className="muted"> ({SOURCE_TEXT[o.source]})</span>{' '}
                <kbd>{DISPUTE_KEYS[i]?.toUpperCase()}</kbd>
              </button>
            ))}
          </div>
        </div>
      )}

      {incident && (
        <>
          <dl className="two-lines" {...lit(incident.evidence)}>
            <dt>Tipo</dt>
            <dd className="address">{labelOf(catalog?.types, incident.category)}</dd>
            <dt>Subtipo</dt>
            <dd>{labelOf(catalog?.subtypes, incident.subtype)}</dd>
          </dl>
          <div className="actions">
            <button type="button" disabled={busy || confirmed} onClick={() => onConfirmType()}>
              Confirmar tipo <kbd>T</kbd>
            </button>
            <TypePicker catalog={catalog} current={incident} busy={busy} onPick={onConfirmType} />
          </div>
        </>
      )}

      {priority && (
        <div className="priority">
          <div className="priority-head">
            <span className={`prio prio-${priority.level} prio-big`}>{priority.level}</span>
            <span className="priority-rule">{priority.rule}</span>
          </div>
          {priority.reasons.length > 0 && (
            <ul className="reasons" aria-label="Por qué">
              {priority.reasons.map((r) => (
                <li key={r.signal_id} {...lit(r.evidence ? [r.evidence] : [])}>
                  <span>
                    {labelOf(catalog?.signals, r.signal_id)}
                    {r.value === 'no' ? ': no' : ''}
                  </span>
                  {r.evidence && <q>{r.evidence.quote}</q>}
                </li>
              ))}
            </ul>
          )}
          {priority.overridden_by_operator && (
            <p className="override">
              Cambiada por el operador
              {priority.overridden_by_operator.from_level
                ? ` (antes ${priority.overridden_by_operator.from_level})`
                : ''}
              : {priority.overridden_by_operator.reason}
            </p>
          )}
          {editingPriority ? (
            <PriorityForm
              current={priority.level}
              busy={busy}
              onCancel={() => onEditPriority(false)}
              onSubmit={(level, reason) => {
                onSetPriority(level, reason)
                onEditPriority(false)
              }}
            />
          ) : (
            <div className="actions">
              <button type="button" className="secondary" onClick={() => onEditPriority(true)}>
                Cambiar prioridad <kbd>P</kbd>
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

interface TypePickerProps {
  catalog: Catalog | null
  current: Incident
  busy: boolean
  onPick: (value: string) => void
}

/** Another tipo (and subtipo) chosen by the operador; picking one also confirms it. */
function TypePicker({ catalog, current, busy, onPick }: TypePickerProps) {
  if (!catalog) return null
  const value = current.subtype ? `${current.category}:${current.subtype}` : current.category
  return (
    <select
      aria-label="Elegir otro tipo"
      disabled={busy}
      value={value}
      onChange={(e) => onPick(e.target.value)}
    >
      {catalog.types.map((t) => (
        <optgroup key={t.id} label={t.label}>
          <option value={t.id}>{t.label} (sin subtipo)</option>
          {catalog.subtypes
            .filter((s) => s.category === t.id)
            .map((s) => (
              <option key={s.id} value={`${t.id}:${s.id}`}>
                {s.label}
              </option>
            ))}
        </optgroup>
      ))}
    </select>
  )
}

interface PriorityFormProps {
  current: Priority
  busy: boolean
  onCancel: () => void
  onSubmit: (level: Priority, reason: string) => void
}

/** Changing the prioridad always asks for a motivo, which goes to the registro de acciones. */
function PriorityForm({ current, busy, onCancel, onSubmit }: PriorityFormProps) {
  const [level, setLevel] = useState<Priority>(current)
  const [reason, setReason] = useState('')
  return (
    <form
      className="priority-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (reason.trim()) onSubmit(level, reason.trim())
      }}
    >
      <div className="levels" role="radiogroup" aria-label="Prioridad">
        {LEVELS.map((l) => (
          <button
            key={l}
            type="button"
            role="radio"
            aria-checked={level === l}
            className={`prio prio-${l} ${level === l ? 'on' : ''}`}
            onClick={() => setLevel(l)}
          >
            {l}
          </button>
        ))}
      </div>
      <div className="correct">
        <input
          autoFocus
          required
          value={reason}
          placeholder="Motivo del cambio (obligatorio)"
          onChange={(e) => setReason(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        />
        <button type="submit" disabled={busy || !reason.trim() || level === current}>
          Guardar
        </button>
      </div>
    </form>
  )
}
