import type { NextQuestion, SignalAnswer } from './api'

export const ANSWER_TEXT: Record<SignalAnswer, string> = {
  si: 'Sí',
  no: 'No',
  no_sabe: 'No sabe',
}

/**
 * What an answer to the próxima pregunta targets: the pregunta clave itself, or, for the
 * universal one, the first señal it still asks about. The ubicación question is answered by
 * confirming or correcting the dirección, not with Sí/No.
 */
export function answerTarget(question: NextQuestion | null): string | null {
  if (!question || question.id === 'ubicacion') return null
  if (question.id === 'universal') return question.signal_ids[0] ?? null
  return question.id
}

/** What skipping the próxima pregunta targets: the pregunta clave or the whole universal. */
export function skipTarget(question: NextQuestion | null): string | null {
  if (!question || question.id === 'ubicacion') return null
  return question.id
}
