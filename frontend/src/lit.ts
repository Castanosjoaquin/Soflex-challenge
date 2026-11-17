import type { Evidence } from './api'

/**
 * Handlers that light a dato's phrases in the relato while the pointer is on it, or the focus:
 * whoever moves with Tab sees the same as whoever moves the mouse.
 */
export function lit(onFocus: (evidence: Evidence[]) => void, evidence: Evidence[]) {
  return {
    onMouseEnter: () => onFocus(evidence),
    onMouseLeave: () => onFocus([]),
    onFocus: () => onFocus(evidence),
    onBlur: () => onFocus([]),
  }
}
