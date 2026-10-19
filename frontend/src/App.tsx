import { useState } from 'react'
import DraftReview from './pages/DraftReview'
import GrantsQueue from './pages/GrantsQueue'

export default function App() {
  const [draftId, setDraftId] = useState<number | null>(null)

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: 24 }}>
      <h1>Grant Agent</h1>
      {draftId === null ? (
        <GrantsQueue onReview={setDraftId} />
      ) : (
        <DraftReview draftId={draftId} onBack={() => setDraftId(null)} />
      )}
    </main>
  )
}
