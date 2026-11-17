import type { CallState, Evidence } from '../api'
import { KEYS, keyLabel } from '../shortcuts'
import { AmpliacionList, CartaView } from './CartaView'

interface Props {
  call: CallState
  busy: boolean
  onDerive: () => void
  onFocus: (evidence: Evidence[]) => void
}

/** The phrases behind a line of the Carta, by its key: the same the cards above light. */
function evidenceOf(call: CallState, key: string): Evidence[] {
  if (key.startsWith('ubicacion.')) return call.location?.evidence ?? []
  if (key.startsWith('incidente.')) return call.incident?.evidence ?? []
  if (key.startsWith('prioridad'))
    return (call.priority?.reasons ?? []).flatMap((r) => (r.evidence ? [r.evidence] : []))
  if (key.startsWith('senal.')) {
    const signal = call.signals.find((s) => `senal.${s.signal_id}` === key)
    return signal?.evidence ? [signal.evidence] : []
  }
  return []
}

/** Etapa ④: the Carta en vivo, the Derivar button and the ampliaciones already sent. */
export function CartaPanel({ call, busy, onDerive, onFocus }: Props) {
  const p1 = call.priority?.level === 'P1'
  return (
    <section className="card carta-panel">
      <div className="card-head">
        <h2>④ Carta de Llamada {call.derived ? '· derivada' : '· en vivo'}</h2>
        {call.derived ? (
          <span className="instruction-done">✔ En la bandeja del despachador</span>
        ) : (
          <div className="derive">
            {call.can_derive && p1 && (
              <span className="derive-p1">P1 · derivá ahora y seguí preguntando</span>
            )}
            {!call.can_derive && (
              <span className="muted">Para derivar, confirmá la ubicación y el tipo</span>
            )}
            <button
              type="button"
              className={call.can_derive ? 'primary' : ''}
              disabled={busy || !call.can_derive}
              onClick={onDerive}
            >
              Derivar <kbd>{keyLabel(KEYS.derive)}</kbd>
            </button>
          </div>
        )}
      </div>
      <CartaView carta={call.carta} onFocus={(key) => onFocus(key ? evidenceOf(call, key) : [])} />
      {call.derived && (
        <div className="carta-sent">
          <h3>Ampliaciones enviadas</h3>
          {call.ampliaciones.length === 0 ? (
            <p className="muted">
              Cada dato que confirmes ahora se manda al despachador como ampliación.
            </p>
          ) : (
            <AmpliacionList ampliaciones={call.ampliaciones} />
          )}
        </div>
      )}
    </section>
  )
}
