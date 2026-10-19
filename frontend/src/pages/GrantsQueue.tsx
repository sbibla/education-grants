import { useCallback, useEffect, useState } from 'react'
import { api, type Queue } from '../api/client'

export default function GrantsQueue() {
  const [queue, setQueue] = useState<Queue | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.queue().then(setQueue).catch((e: Error) => setError(e.message))
  }, [])

  useEffect(load, [load])

  const findNext = async () => {
    setError(null)
    try {
      await api.startSearch()
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!queue) return <p>{error ?? 'Loading…'}</p>

  return (
    <section>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>
          Grants {queue.batch_number ? `— batch ${queue.batch_number}` : ''} ({queue.grants.length}/10)
        </h2>
        <button
          onClick={findNext}
          disabled={!queue.can_search}
          title={queue.search_blocked_reason ?? ''}
        >
          Find next 10
        </button>
      </header>
      {!queue.can_search && queue.search_blocked_reason && <p>{queue.search_blocked_reason}</p>}
      {error && <p role="alert">{error}</p>}
      {queue.grants.length === 0 && <p>No grants yet. Run a search to get started.</p>}
      <ul style={{ listStyle: 'none', padding: 0, display: 'grid', gap: 12 }}>
        {queue.grants.map((g) => (
          <li key={g.id} style={{ border: '1px solid #8884', borderRadius: 8, padding: 12 }}>
            <strong>{g.title}</strong> <small>{g.funder}</small>
            <div>{g.verdict && <em>{g.verdict}</em>}</div>
            <button disabled>Draft</button>
          </li>
        ))}
      </ul>
    </section>
  )
}
