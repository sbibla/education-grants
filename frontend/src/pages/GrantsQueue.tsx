import { useCallback, useEffect, useState } from 'react'
import { api, type Queue } from '../api/client'
import GrantCard from '../components/GrantCard'

const POLL_MS = 2000

interface Props {
  onReview: (draftId: number) => void
}

export default function GrantsQueue({ onReview }: Props) {
  const [queue, setQueue] = useState<Queue | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .queue()
      .then(setQueue)
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(load, [load])

  // Poll while a search or any draft is in progress.
  const inProgress =
    !!queue && (queue.search_running || queue.grants.some((g) => g.draft_status === 'drafting'))
  useEffect(() => {
    if (!inProgress) return
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [inProgress, load])

  const run = async (action: () => Promise<unknown>) => {
    setError(null)
    try {
      await action()
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!queue) return <p>{error ?? 'Loading…'}</p>

  const searchLabel = queue.search_running
    ? 'Searching…'
    : queue.batch_number
      ? 'Find next 10'
      : 'Find first 10'

  return (
    <section>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>
          Grants{queue.batch_number ? ` — batch ${queue.batch_number}` : ''} ({queue.grants.length}/10)
        </h2>
        <button
          onClick={() => run(api.startSearch)}
          disabled={!queue.can_search || queue.search_running}
          title={queue.search_blocked_reason ?? ''}
        >
          {searchLabel}
        </button>
      </header>
      {!queue.can_search && queue.search_blocked_reason && !queue.search_running && (
        <p>
          <small>{queue.search_blocked_reason}</small>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {queue.search_running && queue.grants.length === 0 && <p>Searching for grants — this can take a few minutes.</p>}
      {!queue.search_running && queue.grants.length === 0 && (
        <p>No grants yet. Click “Find first 10” to start.</p>
      )}
      <ul style={{ listStyle: 'none', padding: 0, display: 'grid', gap: 12 }}>
        {queue.grants.map((g) => (
          <GrantCard
            key={g.id}
            grant={g}
            onDraft={(id) => run(() => api.startDraft(id))}
            onReview={onReview}
          />
        ))}
      </ul>
    </section>
  )
}
