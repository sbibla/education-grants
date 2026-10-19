export interface GrantFields {
  deadline?: string | null
  rolling_or_unknown_deadline?: boolean
  amount_min?: number | null
  amount_max?: number | null
  geography?: string | null
}

export interface Grant {
  id: number
  title: string
  funder: string | null
  url: string
  categories: string[]
  fields: GrantFields
  verdict: string | null
  reasons: { text: string; source_quote?: string }[]
  draft_id: number | null
  draft_status: 'drafting' | 'drafted' | 'approved' | 'submitted' | 'failed' | null
}

export interface Queue {
  batch_number: number | null
  grants: Grant[]
  search_running: boolean
  can_search: boolean
  search_blocked_reason: string | null
}

export interface DraftField {
  id: number
  question: string
  answer: string
  sources: unknown[]
  needs_human: boolean
}

export interface Draft {
  id: number
  grant_id: number
  version: number
  status: string
  fields: DraftField[]
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
  startDraft: (grantId: number) =>
    request<{ draft_id: number; status: string }>(`/grants/${grantId}/draft`, { method: 'POST' }),
  draft: (draftId: number) => request<Draft>(`/drafts/${draftId}`),
}
