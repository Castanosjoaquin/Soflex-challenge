import { useEffect, useState } from 'react'
import { api, type DerivedCarta } from './api'
import { AmpliacionList, CartaView } from './components/CartaView'
import { formatTime } from './format'

const POLL_MS = 2000

/** Bandeja del despachador: the Cartas derivadas, the most recent first, refreshed every 2 s. */
export default function Despacho() {
  const [cartas, setCartas] = useState<DerivedCarta[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .dispatch()
        .then((c) => {
          if (!alive) return
          setCartas(c)
          setError(null)
        })
        .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)))
    void load()
    const timer = setInterval(() => void load(), POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  return (
    <div className="shell">
      <header className="topbar">
        <h1>Bandeja del despachador</h1>
        <a className="badge" href="/">
          Ir al panel del operador
        </a>
      </header>
      {error && <p className="error">No se pudo actualizar la bandeja: {error}</p>}
      <main className="despacho">
        {cartas === null ? (
          <p className="muted">Cargando…</p>
        ) : cartas.length === 0 ? (
          <p className="muted">Todavía no llegó ninguna Carta de Llamada.</p>
        ) : (
          cartas.map((c) => {
            const level = c.carta.priority.find((d) => d.key === 'prioridad')?.value
            return (
              <article key={c.call_id} className="card despacho-carta">
                <div className="card-head">
                  <h2>
                    {level && <span className={`prio prio-${level}`}>{level}</span>} Línea {c.line} ·
                    recibida {formatTime(c.derived_at)}
                  </h2>
                  {c.ampliaciones.length > 0 && (
                    <span className="badge">
                      {c.ampliaciones.length}{' '}
                      {c.ampliaciones.length === 1 ? 'ampliación' : 'ampliaciones'}
                    </span>
                  )}
                </div>
                <CartaView carta={c.carta} />
                {c.ampliaciones.length > 0 && (
                  <div className="carta-sent">
                    <h3>Ampliaciones</h3>
                    <AmpliacionList ampliaciones={c.ampliaciones} />
                  </div>
                )}
              </article>
            )
          })
        )}
      </main>
    </div>
  )
}
