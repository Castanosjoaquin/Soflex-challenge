import type { CallState, NextQuestion, SignalAnswer, StageId } from '../api'
import { ANSWER_KEYS, ANSWER_TEXT, answerTarget } from '../questions'

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
  busy: boolean
  onAnswer: (value: SignalAnswer) => void
  onSkip: () => void
}

export function StageBar({ stages, nextQuestion, busy, onAnswer, onSkip }: Props) {
  const answerable = answerTarget(nextQuestion) !== null
  return (
    <div className="stagebar">
      <ol className="stages" aria-label="Etapas del protocolo">
        {stages.map((stage) => (
          <li
            key={stage.id}
            className={`stage stage-${stage.status}${stage.alert ? ' stage-alert' : ''}`}
          >
            <span>{LABELS[stage.id]}</span>
            <small>{stage.status === 'hecha' ? '✓ ' : ''}{STATUS_TEXT[stage.status]}</small>
          </li>
        ))}
      </ol>
      {nextQuestion && (
        <div className="next-question" role="status">
          <p>
            <small>Próxima pregunta</small>
            {nextQuestion.text}
          </p>
          {answerable && (
            <div className="actions">
              {ANSWER_KEYS.map(([key, value]) => (
                <button key={value} type="button" disabled={busy} onClick={() => onAnswer(value)}>
                  {ANSWER_TEXT[value]} <kbd>{key}</kbd>
                </button>
              ))}
              <button type="button" className="secondary" disabled={busy} onClick={onSkip}>
                Saltear <kbd>S</kbd>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
