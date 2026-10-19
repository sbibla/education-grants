import { useEffect, useState } from 'react'
import { api, type Draft } from '../api/client'

interface Props {
  draftId: number
  onBack: () => void
}

export default function DraftReview({ draftId, onBack }: Props) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [reviewed, setReviewed] = useState<Set<number>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = (d: Draft) => {
    setDraft(d)
    setAnswers(Object.fromEntries(d.fields.map((f) => [f.id, f.answer])))
    setReviewed(new Set())
  }

  useEffect(() => {
    api
      .draft(draftId)
      .then(load)
      .catch((e: Error) => setError(e.message))
  }, [draftId])

  if (!draft) return <p>{error ?? 'Loading…'}</p>

  const locked = draft.status === 'approved' || draft.status === 'submitted'
  const changed = draft.fields.filter((f) => answers[f.id] !== f.answer)
  const dirty = changed.length > 0

  const act = async (fn: () => Promise<Draft>) => {
    setBusy(true)
    setError(null)
    try {
      load(await fn())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const approve = () =>
    act(() =>
      api.approve(draft.id, {
        edits: changed.map((f) => ({ id: f.id, answer: answers[f.id] })),
        reviewed_ids: [...reviewed],
      }),
    )

  const toggleReviewed = (id: number) =>
    setReviewed((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })

  return (
    <section>
      <button onClick={onBack}>← Back to grants</button>
      <h2>{draft.grant_title}</h2>
      <p>
        <small>
          <a href={draft.grant_url} target="_blank" rel="noreferrer">
            Grant page
          </a>{' '}
          · Draft #{draft.id} · {draft.status}
        </small>
      </p>

      {draft.fields.map((f) => {
        const edited = answers[f.id] !== f.answer
        const flagged = f.needs_human && !edited
        return (
          <div key={f.id} style={{ margin: '16px 0' }}>
            <label htmlFor={`f${f.id}`}>
              <strong>{f.question}</strong>
            </label>
            {flagged && !locked && <small> · needs your input</small>}
            <textarea
              id={`f${f.id}`}
              value={answers[f.id] ?? ''}
              disabled={locked}
              rows={5}
              style={{
                width: '100%',
                boxSizing: 'border-box',
                borderColor: flagged && !locked ? 'orange' : undefined,
              }}
              onChange={(e) => setAnswers({ ...answers, [f.id]: e.target.value })}
            />
            {flagged && !locked && (
              <label>
                <input
                  type="checkbox"
                  checked={reviewed.has(f.id)}
                  onChange={() => toggleReviewed(f.id)}
                />{' '}
                I’ve reviewed this answer as written
              </label>
            )}
          </div>
        )
      })}

      {error && <p role="alert">{error}</p>}

      {!locked && (
        <button disabled={busy} onClick={approve}>
          {dirty ? 'Save changes & submit' : 'Submit as-is'}
        </button>
      )}

      {locked && (
        <div style={{ border: '1px solid #8884', borderRadius: 8, padding: 12 }}>
          <strong>
            {draft.status === 'submitted' ? 'Marked as submitted.' : 'Approved and ready to send.'}
          </strong>
          <p>
            <a href={api.exportUrl(draft.id)}>Download application (.docx)</a>
          </p>
          <p>
            Send via: <b>{draft.submission_method ?? 'unknown'}</b>
            {draft.submission_target && <> — {draft.submission_target}</>}
          </p>
          {draft.status === 'approved' && (
            <>
              <p>
                <small>
                  The agent doesn’t send anything itself. After you send the application, confirm
                  below.
                </small>
              </p>
              <button disabled={busy} onClick={() => act(() => api.markSubmitted(draft.id))}>
                I’ve submitted it
              </button>
            </>
          )}
        </div>
      )}
    </section>
  )
}
