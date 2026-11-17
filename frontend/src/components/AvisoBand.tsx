import type { Aviso, Evidence, Resolution } from '../api'

interface Props {
  avisos: Aviso[]
  busy: boolean
  onResolve: (avisoId: string, resolution: Resolution) => void
  onFocus: (evidence: Evidence[]) => void
}

const TITLE: Record<Aviso['kind'], string> = {
  contradiccion: 'Contradicción',
  senal_p1: 'Señal de P1',
}

/**
 * The first aviso still pending: a contradicción or a señal de P1 over a prioridad lowered by
 * hand. One of the only two avisos that interrupt (DESIGN §Paso 8), so it is a band in plain
 * sight, not a modal: the operador keeps working and resolves it with A or M.
 */
export function AvisoBand({ avisos, busy, onResolve, onFocus }: Props) {
  const pending = avisos.filter((a) => a.status === 'pendiente')
  const aviso = pending[0]
  if (!aviso) return null
  const accept = aviso.kind === 'senal_p1' ? `Pasar a ${aviso.after}` : `Tomar ${aviso.after}`
  const keep = aviso.kind === 'senal_p1' ? `Dejar ${aviso.before}` : `Mantener ${aviso.before}`
  return (
    <div
      className="aviso-band"
      role="alert"
      onMouseEnter={() => onFocus(aviso.evidence)}
      onMouseLeave={() => onFocus([])}
    >
      <p>
        <small>
          {TITLE[aviso.kind]} · {aviso.label}
          {pending.length > 1 ? ` · 1 de ${pending.length}` : ''}
        </small>
        {aviso.text}
        {aviso.evidence.length > 0 && (
          <q className="aviso-quote">{aviso.evidence.map((e) => e.quote).join(' … ')}</q>
        )}
      </p>
      <div className="aviso-actions">
        <button type="button" disabled={busy} onClick={() => onResolve(aviso.id, 'aceptar')}>
          {accept} <kbd>A</kbd>
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy}
          onClick={() => onResolve(aviso.id, 'mantener')}
        >
          {keep} <kbd>M</kbd>
        </button>
      </div>
    </div>
  )
}
