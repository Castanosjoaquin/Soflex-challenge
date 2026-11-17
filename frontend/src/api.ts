// Typed client for the backend API. Shapes mirror the Pydantic models in backend/app/api.py.

export type Priority = 'P1' | 'P2' | 'P3' | 'P4'

export interface Health {
  status: string
  provider: 'mock' | 'openai_compat'
  catalog_size: number
}

export interface SampleCall {
  id: string
  category: string
  subcategory: string
  priority: Priority
  transcript: string
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`)
  return (await res.json()) as T
}

export const api = {
  health: () => getJson<Health>('/api/health'),
  samples: () => getJson<SampleCall[]>('/api/samples'),
}
