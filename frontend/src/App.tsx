import { useEffect, useState } from 'react'
import { api, type Health, type SampleCall } from './api'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [samples, setSamples] = useState<SampleCall[]>([])
  const [selected, setSelected] = useState<SampleCall | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.health(), api.samples()])
      .then(([h, s]) => {
        setHealth(h)
        setSamples(s)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  return (
    <div className="shell">
      <header className="topbar">
        <h1>Copiloto de Sala</h1>
        {health && (
          <span className="badge" title="Proveedor de extracción activo">
            {health.provider === 'mock' ? 'Modo simulado' : 'LLM real'} · {health.catalog_size}{' '}
            casos de referencia
          </span>
        )}
      </header>

      {error && <p className="error">Backend no disponible: {error}</p>}

      <main className="layout">
        <aside className="samples">
          <h2>Llamadas de prueba</h2>
          <ul>
            {samples.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={selected?.id === s.id ? 'active' : ''}
                  onClick={() => setSelected(s)}
                >
                  <span className={`prio prio-${s.priority}`}>{s.priority}</span>
                  {s.subcategory}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="transcript">
          <h2>Transcripción</h2>
          {selected ? (
            <p>{selected.transcript}</p>
          ) : (
            <p className="muted">Elegí una llamada de prueba para empezar.</p>
          )}
        </section>
      </main>
    </div>
  )
}
