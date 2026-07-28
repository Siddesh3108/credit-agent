import { useEffect, useState } from 'react'
import { apiClient } from '../services/apiClient'

export default function AdminPanel({ token }) {
  const [conversationId, setConversationId] = useState('')
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setStatus('Enter a conversation ID to approve or deny a pending review.')
  }, [])

  const handleApprove = async () => {
    if (!conversationId.trim()) return
    setError(null)
    try {
      await apiClient.adminResolve(conversationId, token, 'approved')
      setStatus('Decision approved.')
    } catch (e) {
      setError(e.message)
    }
  }

  const handleDeny = async () => {
    if (!conversationId.trim()) return
    setError(null)
    try {
      await apiClient.adminResolve(conversationId, token, 'denied')
      setStatus('Decision denied.')
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div style={{ maxWidth: 560, margin: '60px auto', padding: 20 }}>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 24 }}>Admin Review</h1>
      <p style={{ color: 'var(--ink-700)', fontSize: 14 }}>
        Enter a conversation ID from a pending review, then approve or deny the request as an admin.
      </p>
      <div style={{ display: 'grid', gap: 12, marginTop: 20 }}>
        <input
          value={conversationId}
          onChange={(e) => setConversationId(e.target.value)}
          placeholder="Conversation ID"
          style={{ padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--line-300)' }}
        />
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={handleApprove}
            style={{ flex: 1, padding: '10px 14px', borderRadius: 'var(--radius-sm)', border: 'none', background: 'var(--trust-700)', color: 'white' }}
          >
            Approve
          </button>
          <button
            onClick={handleDeny}
            style={{ flex: 1, padding: '10px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--line-300)', background: 'transparent', color: 'var(--ink-900)' }}
          >
            Deny
          </button>
        </div>
        {status && <div style={{ color: 'var(--ink-900)' }}>{status}</div>}
        {error && <div style={{ color: 'var(--alert-600)' }}>{error}</div>}
      </div>
    </div>
  )
}
