import type { CallState, StageId } from '../api'

const LABELS: Record<StageId, string> = {
  ubicar: '① Ubicar',
  que_pasa: '② ¿Qué pasa?',
  preguntas: '③ Preguntas clave',
  derivar: '④ Derivar',
  instrucciones: '⑤ Instrucciones',
}

const STATUS_TEXT = { hecha: 'hecha', actual: 'actual', pendiente: 'pendiente' } as const

export function StageBar({ stages }: { stages: CallState['stages'] }) {
  return (
    <ol className="stages" aria-label="Etapas del protocolo">
      {stages.map((stage) => (
        <li key={stage.id} className={`stage stage-${stage.status}`}>
          <span>{LABELS[stage.id]}</span>
          <small>{stage.status === 'hecha' ? '✓ ' : ''}{STATUS_TEXT[stage.status]}</small>
        </li>
      ))}
    </ol>
  )
}
