import type { Grant } from '../api/client'

const money = (n?: number | null) => (n ? `$${n.toLocaleString()}` : null)

function amount(g: Grant) {
  const { amount_min: lo, amount_max: hi } = g.fields
  if (lo && hi && lo !== hi) return `${money(lo)}–${money(hi)}`
  return money(hi ?? lo) ?? 'Amount not stated'
}

function deadline(g: Grant) {
  if (g.fields.deadline) return `Due ${g.fields.deadline}`
  return g.fields.rolling_or_unknown_deadline ? 'Rolling / unknown deadline' : 'Deadline not stated'
}

interface Props {
  grant: Grant
  onDraft: (grantId: number) => void
  onReview: (draftId: number) => void
}

export default function GrantCard({ grant: g, onDraft, onReview }: Props) {
  const drafting = g.draft_status === 'drafting'
  const filled = g.draft_status === 'drafted' || g.draft_status === 'approved'

  return (
    <li style={{ border: '1px solid #8884', borderRadius: 8, padding: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <a href={g.url} target="_blank" rel="noreferrer">
            <strong>{g.title}</strong>
          </a>
          {g.funder && <small> · {g.funder}</small>}
          <div>
            <small>
              {amount(g)} · {deadline(g)}
            </small>
          </div>
          <div>
            {g.verdict && <em>{g.verdict}</em>} {g.categories.map((c) => `#${c}`).join(' ')}
          </div>
        </div>
        <div style={{ whiteSpace: 'nowrap' }}>
          {filled ? (
            <button onClick={() => g.draft_id && onReview(g.draft_id)}>Review draft</button>
          ) : (
            <button disabled={drafting} onClick={() => onDraft(g.id)}>
              {drafting ? 'Drafting…' : 'Draft'}
            </button>
          )}
        </div>
      </div>
      {g.reasons.length > 0 && (
        <details>
          <summary>Why OPEF qualifies</summary>
          <ul>
            {g.reasons.map((r, i) => (
              <li key={i}>
                {r.text}
                {r.source_quote && <blockquote style={{ margin: '4px 0' }}>{r.source_quote}</blockquote>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  )
}
