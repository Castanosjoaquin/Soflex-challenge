import type { SignalAnswer } from './api'

/**
 * Every keyboard shortcut of the panel, in one place: the handler in App, the <kbd> hints on
 * screen and the ayuda (?) all read it, so a hint can never name a key that does something else.
 * One key, one action: no key changes meaning with what is on screen.
 */
export const KEYS = {
  pause: ' ',
  nextTurn: 'n',
  slower: 'z',
  faster: 'x',
  confirmLocation: 'c',
  correctLocation: 'u',
  confirmType: 't',
  otherType: 'e',
  priority: 'p',
  skip: 's',
  premark: 'v',
  read: 'l',
  avisoAccept: 'a',
  avisoKeep: 'm',
  derive: 'd',
  note: 'o',
  trace: 'r',
  close: 'q',
  help: '?',
} as const

/** One key per option of a tipo en disputa, in the order of `TypeDispute.options`. */
export const DISPUTE_KEYS = ['f', 'g']

/** Keys that answer the próxima pregunta, in the order the buttons show them. */
export const ANSWER_KEYS: [string, SignalAnswer][] = [
  ['1', 'si'],
  ['2', 'no'],
  ['3', 'no_sabe'],
]

const ALL_KEYS = [...Object.values(KEYS), ...DISPUTE_KEYS, ...ANSWER_KEYS.map(([k]) => k)]
if (new Set(ALL_KEYS).size !== ALL_KEYS.length) {
  throw new Error(`Hay una tecla con dos acciones: ${ALL_KEYS.join(' ')}`)
}

/** How a key is printed in a <kbd>. */
export function keyLabel(key: string): string {
  if (key === ' ') return 'Espacio'
  return key.length === 1 ? key.toUpperCase() : key
}

interface Shortcut {
  keys: string[]
  text: string
}

/** The ayuda (?), in the order the operador meets the actions on screen. */
export const HELP: { title: string; items: Shortcut[] }[] = [
  {
    title: 'Ubicar y qué pasa',
    items: [
      { keys: [KEYS.confirmLocation], text: 'Confirmar la ubicación' },
      { keys: [KEYS.correctLocation], text: 'Corregir la ubicación (Enter guarda, Esc cancela)' },
      { keys: [KEYS.confirmType], text: 'Confirmar el tipo' },
      { keys: [KEYS.otherType], text: 'Elegir otro tipo o subtipo de la lista' },
      { keys: DISPUTE_KEYS, text: 'Tipo en disputa: elegir la primera o la segunda opción' },
      { keys: [KEYS.priority], text: 'Cambiar la prioridad (con motivo)' },
    ],
  },
  {
    title: 'Preguntas e instrucciones',
    items: [
      {
        keys: ANSWER_KEYS.map(([k]) => k),
        text: 'Responder la próxima pregunta: Sí, No, No sabe',
      },
      { keys: [KEYS.skip], text: 'Saltear la próxima pregunta' },
      { keys: [KEYS.premark], text: 'Confirmar la primera pre-marca' },
      { keys: [KEYS.read], text: 'Marcar leída la próxima instrucción (la crítica primero)' },
      { keys: [KEYS.avisoAccept, KEYS.avisoKeep], text: 'Aviso: tomar el valor nuevo o mantener' },
    ],
  },
  {
    title: 'Derivar y cerrar',
    items: [
      { keys: [KEYS.derive], text: 'Derivar la Carta al despachador' },
      { keys: [KEYS.note], text: 'Escribir una nota (Enter la agrega, Esc vuelve)' },
      { keys: [KEYS.close], text: 'Cerrar la llamada (pide confirmación)' },
    ],
  },
  {
    title: 'Reproducción y vista',
    items: [
      { keys: [KEYS.pause], text: 'Pausa / seguir' },
      { keys: [KEYS.nextTurn], text: 'Siguiente turno' },
      {
        keys: [KEYS.slower, KEYS.faster],
        text: 'Más lento / más rápido (Lenta, Normal, ×2, ×4)',
      },
      { keys: [KEYS.trace], text: 'Abrir o cerrar el detalle técnico' },
      { keys: [KEYS.help, 'Esc'], text: 'Mostrar u ocultar esta ayuda' },
    ],
  },
]
