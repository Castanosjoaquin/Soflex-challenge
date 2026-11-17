import { HELP, keyLabel } from '../shortcuts'

interface Props {
  onClose: () => void
}

/**
 * The ayuda (?): every shortcut of the panel. It does not block the panel: the keys keep
 * working underneath, and ? or Esc close it.
 */
export function ShortcutHelp({ onClose }: Props) {
  return (
    <aside className="shortcut-help" role="dialog" aria-label="Atajos de teclado">
      <header className="card-head">
        <h2>Atajos de teclado</h2>
        <button type="button" className="secondary" onClick={onClose}>
          Cerrar <kbd>Esc</kbd>
        </button>
      </header>
      <div className="shortcut-groups">
        {HELP.map((group) => (
          <section key={group.title}>
            <h3>{group.title}</h3>
            <dl>
              {group.items.map((item) => (
                <div key={item.text} className="shortcut">
                  <dt>
                    {item.keys.map((k) => (
                      <kbd key={k}>{keyLabel(k)}</kbd>
                    ))}
                  </dt>
                  <dd>{item.text}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
      <p className="muted legend">
        Una tecla, una acción: ninguna cambia de sentido según lo que haya en pantalla. Con Tab se
        llega a cualquier botón y con Enter se activa. Mientras escribís en una caja, las teclas
        escriben; Esc vuelve a los atajos.
      </p>
    </aside>
  )
}
