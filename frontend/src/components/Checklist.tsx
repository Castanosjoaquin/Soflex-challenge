import type {
  ChecklistItem,
  Evidence,
  QuestionStatus,
  SignalAlternative,
  SignalAnswer,
} from '../api'
import { lit } from '../lit'
import { ANSWER_TEXT } from '../questions'
import { KEYS, keyLabel } from '../shortcuts'

const STATUS_MARK: Record<QuestionStatus, string> = {
  pendiente: '○',
  pre_marcada: '◐',
  respondida: '✔',
  salteada: '↷',
}

const STATUS_TEXT: Record<QuestionStatus, string> = {
  pendiente: 'Pendiente',
  pre_marcada: 'Pre-marcada: falta confirmar',
  respondida: 'Respondida',
  salteada: 'Salteada',
}

interface Props {
  items: ChecklistItem[]
  /** The pregunta clave asked now, highlighted in the list. */
  nextId: string | null
  /** What the other lector read, by señal, when the two lectores disagree. */
  alternatives: Record<string, SignalAlternative>
  busy: boolean
  onConfirm: (questionId: string) => void
  onAnswer: (questionId: string, value: SignalAnswer) => void
  onFocus: (evidence: Evidence[]) => void
}

export function Checklist({
  items,
  nextId,
  alternatives,
  busy,
  onConfirm,
  onAnswer,
  onFocus,
}: Props) {
  if (items.length === 0) {
    return (
      <section className="card">
        <h2>③ Preguntas clave</h2>
        <p className="muted">Aparecen cuando se sabe qué tipo de incidente es.</p>
      </section>
    )
  }

  const firstPremark = items.find((i) => i.status === 'pre_marcada')?.question_id

  return (
    <section className="card">
      <h2>③ Preguntas clave</h2>
      <ul className="checklist">
        {items.map((item) => {
          const alternative =
            item.status === 'pre_marcada' ? alternatives[item.signal_id] : undefined
          const phrases = [
            ...(item.evidence ? [item.evidence] : []),
            ...(alternative ? [alternative.evidence] : []),
          ]
          return (
            <li
              key={item.question_id}
              className={`question question-${item.status}${item.question_id === nextId ? ' next' : ''}`}
              tabIndex={phrases.length > 0 ? 0 : undefined}
              {...lit(onFocus, phrases)}
            >
              <span className="question-mark" title={STATUS_TEXT[item.status]}>
                {STATUS_MARK[item.status]}
              </span>
              <div className="question-body">
                <span className="question-text">
                  {item.text}
                  {item.critical && <span className="critical" title="Crítica">*</span>}
                </span>
                {item.value && item.status !== 'pendiente' && (
                  <span className="question-answer">
                    {ANSWER_TEXT[item.value]}
                    {item.evidence ? (
                      <q>{item.evidence.quote}</q>
                    ) : (
                      item.source === 'operador' && <span className="muted"> · operador</span>
                    )}
                  </span>
                )}
                {alternative && (
                  <span className="question-answer alternative">
                    Otro lector: {ANSWER_TEXT[alternative.value]}
                    <q>{alternative.evidence.quote}</q>
                  </span>
                )}
                {item.status !== 'respondida' && (
                  <span className="question-quick">
                    {item.status === 'pre_marcada' && (
                      <button
                        type="button"
                        className="question-confirm"
                        disabled={busy}
                        onClick={() => onConfirm(item.question_id)}
                      >
                        Confirmar{' '}
                        {item.question_id === firstPremark && <kbd>{keyLabel(KEYS.premark)}</kbd>}
                      </button>
                    )}
                    {(['si', 'no', 'no_sabe'] as const).map((value) => (
                      <button
                        key={value}
                        type="button"
                        className="secondary"
                        disabled={busy}
                        title={item.status === 'pre_marcada' ? 'Corregir la pre-marca' : undefined}
                        onClick={() => onAnswer(item.question_id, value)}
                      >
                        {value === 'no_sabe' ? 'NS' : ANSWER_TEXT[value]}
                      </button>
                    ))}
                  </span>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      <p className="muted legend">* crítica · ◐ pre-marcada desde el relato</p>
    </section>
  )
}
