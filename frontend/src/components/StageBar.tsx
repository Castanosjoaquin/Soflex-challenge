import type { CallState, NextQuestion, StageId } from '../api'

const LABELS: Record<StageId, string> = {
  ubicar: '① Ubicar',
  que_pasa: '② ¿Qué pasa?',
  preguntas: '③ Preguntas clave',
  derivar: '④ Derivar',
  instrucciones: '⑤ Instrucciones',
}

const STATUS_TEXT = { hecha: 'hecha', actual: 'actual', pendiente: 'pendiente' } as const

interface Props {
  stages: CallState['stages']
  nextQuestion: NextQuestion | null
}

export function StageBar({ stages, nextQuestion }: Props) {
  return (
    <div className="stagebar">
      <ol className="stages" aria-label="Etapas del protocolo">
        {stages.map((stage) => (
          <li key={stage.id} className={`stage stage-${stage.status}`}>
            <span>{LABELS[stage.id]}</span>
            <small>{stage.status === 'hecha' ? '✓ ' : ''}{STATUS_TEXT[stage.status]}</small>
          </li>
        ))}
      </ol>
      {nextQuestion && (
        <p className="next-question" role="status">
          <small>Próxima pregunta</small>
          {nextQuestion.text}
        </p>
      )}
    </div>
  )
}
