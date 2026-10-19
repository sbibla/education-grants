import { useEffect, useState } from 'react'
import { api, type Draft } from '../api/client'

interface Props {
  draftId: number
  onBack: () => void
}

// Read-only view for now; editing, versioning, and submit arrive in phase 5.
export default function DraftReview({ draftId, onBack }: Props) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .draft(draftId)
      .then(setDraft)
      .catch((e: Error) => setError(e.message))
  }, [draftId])

  if (!draft) return <p>{error ?? 'Loading…'}</p>

  return (
    <section>
      <button onClick={onBack}>← Back to grants</button>
      <h2>Draft #{draft.id}</h2>
      {draft.fields.map((f) => (
        <div key={f.id} style={{ margin: '16px 0' }}>
          <strong>{f.question}</strong>
          {f.needs_human && <small> · needs your input</small>}
          <p style={{ whiteSpace: 'pre-wrap' }}>{f.answer}</p>
        </div>
      ))}
    </section>
  )
}
