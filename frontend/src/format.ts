import type { Location } from './api'

/** One-line dirección for the ubicación card, e.g. "Av. Corrientes 1540, casi Montevideo". */
export function formatAddress(location: Location): string {
  const street = location.street_official ?? location.street
  const { number } = location
  const cross = location.cross_streets_official.length
    ? location.cross_streets_official
    : location.cross_streets
  const parts: string[] = []
  if (street) {
    if (number?.kind === 'esquina' && cross.length > 0) {
      parts.push(`${street} y ${cross[0]}`)
    } else {
      let head = street
      if (number?.kind === 'exacta' && number.value !== null) head += ` ${number.value}`
      if (number?.kind === 'al' && number.value !== null) head += ` al ${number.value}`
      if (number?.kind === 'km' && number.value !== null) head += ` km ${number.value}`
      if (number?.kind === 'sn') head += ' s/n'
      parts.push(head)
      if (cross.length === 1) parts.push(`casi ${cross[0]}`)
      if (cross.length >= 2) parts.push(`entre ${cross[0]} y ${cross[1]}`)
    }
  }
  if (location.landmark) parts.push(location.landmark)
  return parts.join(', ') || '—'
}

/** Hour of an ISO timestamp as the sala reads it, e.g. "14:32:05". */
export function formatTime(at: string): string {
  return new Date(at).toLocaleTimeString('es-AR', { hour12: false })
}
