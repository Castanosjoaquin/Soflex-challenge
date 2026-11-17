import type { CallState } from '../api'
import { AmpliacionList, CartaView } from './CartaView'

interface Props {
  call: CallState
  busy: boolean
  onDerive: () => void
}

/** Etapa ④: the Carta en vivo, the Derivar button and the ampliaciones already sent. */
export function CartaPanel({ call, busy, onDerive }: Props) {
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
              Derivar <kbd>D</kbd>
            </button>
          </div>
        )}
      </div>
      <CartaView carta={call.carta} />
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
