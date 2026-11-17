import type { Ampliacion, Carta, CartaDato, CartaOrigin } from '../api'
import { formatTime } from '../format'

const ORIGIN_TEXT: Record<CartaOrigin, string> = {
  llamante: 'dijo el llamante',
  sistema: 'del sistema',
  operador: 'cargado por el operador',
}

const SECTIONS: { key: keyof Omit<Carta, 'missing'>; title: string; empty: string }[] = [
  { key: 'where', title: 'Dónde', empty: 'Sin ubicación confirmada' },
  { key: 'what', title: 'Qué pasa', empty: 'Sin tipo confirmado' },
  { key: 'priority', title: 'Prioridad', empty: '—' },
  { key: 'at_risk', title: 'Quién está en riesgo', empty: 'Nada confirmado todavía' },
  { key: 'instructions', title: 'Qué se le indicó al llamante', empty: 'Ninguna instrucción leída' },
]

function Dato({ dato }: { dato: CartaDato }) {
  return (
    <li className={`carta-dato origin-${dato.origin}`}>
      <span className="carta-label">{dato.label}</span>
      <span className="carta-value">{dato.value}</span>
      {!dato.confirmed && <span className="carta-unconfirmed">sin confirmar</span>}
      <span className="carta-origin">
        {ORIGIN_TEXT[dato.origin]}
        {dato.quote && dato.quote !== dato.value && <q>{dato.quote}</q>}
      </span>
    </li>
  )
}

/** The Carta de Llamada in plain words, for the operador and for the despachador alike. */
export function CartaView({ carta }: { carta: Carta }) {
  return (
    <div className="carta">
      {SECTIONS.map(({ key, title, empty }) => (
        <section key={key} className="carta-section">
          <h3>{title}</h3>
          {carta[key].length === 0 ? (
            <p className="muted">{empty}</p>
          ) : (
            <ul>
              {carta[key].map((dato) => (
                <Dato key={dato.key} dato={dato} />
              ))}
            </ul>
          )}
        </section>
      ))}
      <section className="carta-section carta-missing">
        <h3>Qué falta preguntar</h3>
        {carta.missing.length === 0 ? (
          <p className="muted">Nada pendiente</p>
        ) : (
          <ul>
            {carta.missing.map((m) => (
              <li key={m.text}>
                {m.text}
                {m.skipped && <span className="carta-skipped"> · salteada</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

/** Ampliaciones in order: what changed in the Carta, with the value before and after. */
export function AmpliacionList({ ampliaciones }: { ampliaciones: Ampliacion[] }) {
  return (
    <ol className="ampliaciones">
      {ampliaciones.map((a, i) => (
        <li key={`${a.at}-${i}`}>
          <span className="ampliacion-at">Ampliación {i + 1} · {formatTime(a.at)}</span>
          <ul>
            {a.changes.map((c) => (
              <li key={c.key}>
                <strong>{c.label}:</strong>{' '}
                {c.after ?? <em>ya no corresponde</em>}
                {c.before !== null && c.after !== null && (
                  <span className="muted"> (antes: {c.before})</span>
                )}
                {c.before !== null && c.after === null && (
                  <span className="muted"> (era: {c.before})</span>
                )}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  )
}
