export interface Grant {
  id: number
  title: string
  funder: string | null
  url: string
  categories: string[]
  fields: Record<string, unknown>
  verdict: string | null
  reasons: { text: string; source_quote?: string }[]
}

export interface Queue {
  batch_number: number | null
  grants: Grant[]
  can_search: boolean
  search_blocked_reason: string | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `Request failed: ${res.status}`)
  }
  return res.json()
}

export const api = {
  queue: () => request<Queue>('/grants/queue'),
  startSearch: () => request<{ search_run_id: number }>('/search-runs', { method: 'POST' }),
}
