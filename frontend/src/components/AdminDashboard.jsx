import { useEffect, useState } from 'react'
import { apiClient } from '../services/apiClient'

export default function AdminDashboard({ token }) {
  const [accountRef, setAccountRef] = useState('')
  const [requests, setRequests] = useState([])
  const [selectedConversation, setSelectedConversation] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [status, setStatus] = useState('Enter a customer account reference to view requests.')
  const [error, setError] = useState(null)
  const [auditTrail, setAuditTrail] = useState(null)
  const [convData, setConvData] = useState(null)
  const [resolving, setResolving] = useState(false)

  useEffect(() => {
    setTranscript(null)
    setSelectedConversation(null)
    setAuditTrail(null)
    setConvData(null)
  }, [])

  const [escalationTickets, setEscalationTickets] = useState([])

  const searchRequests = async () => {
    if (!accountRef.trim()) return
    setError(null)
    setStatus('Loading requests...')
    setEscalationTickets([])
    try {
      const data = await apiClient.getAccountRequests(accountRef.trim(), token)
      setRequests(data.requests)
      setStatus(data.requests.length ? `${data.requests.length} request(s) found.` : 'No requests found for this account.')
    } catch (e) {
      setError(e.message)
      setRequests([])
      setStatus('Failed to load account requests.')
    }
  }

  const loadEscalations = async () => {
    setError(null)
    setStatus('Loading escalations...')
    setRequests([])
    try {
      const data = await apiClient.getEscalations(token)
      const ticketsArr = Object.entries(data.tickets).map(([ref, t]) => ({
        ticket_ref: ref,
        conversation_id: t.payload.conversation_id,
        status: t.status,
        started_at: new Date().toISOString(), // we don't have exact start time in ticket payload easily, just for sort
        outcome: t.resolution_note || t.status
      }))
      setEscalationTickets(ticketsArr)
      setStatus(ticketsArr.length ? `${ticketsArr.length} escalation(s) found.` : 'No escalations found.')
    } catch (e) {
      setError(e.message)
      setEscalationTickets([])
      setStatus('Failed to load escalations.')
    }
  }

  const showTranscript = async (conversationId) => {
    setError(null)
    setStatus('Loading transcript...')
    setAuditTrail(null)
    try {
      const [data, audit] = await Promise.all([
        apiClient.getConversationTranscript(conversationId, token),
        apiClient.getAuditTrail(conversationId),
      ])
      setTranscript(data)
      setSelectedConversation(conversationId)
      setAuditTrail(audit)
      
      try {
        const convRes = await apiClient.getConversation(conversationId, token)
        setConvData(convRes)
      } catch (e) {
        console.warn("Could not fetch running graph state for conversation (might be mock data): ", e.message)
        setConvData({ status: data.status })
      }
      
      setStatus(`Transcript loaded for ${conversationId}`)
    } catch (e) {
      setError(e.message)
      setTranscript(null)
      setSelectedConversation(null)
      setAuditTrail(null)
      setConvData(null)
      setStatus('Failed to load transcript.')
    }
  }

  const handleResolve = async (outcome) => {
    if (!selectedConversation) return
    setResolving(true)
    setError(null)
    try {
      await apiClient.adminResolve(selectedConversation, token, outcome, 'Reviewed by admin')
      await showTranscript(selectedConversation)
      if (requests.length) await searchRequests()
      if (escalationTickets.length) await loadEscalations()
    } catch(e) {
      setError(e.message)
    } finally {
      setResolving(false)
    }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: 20, padding: 24, height: '100%' }}>
      <section style={{ border: '1px solid var(--line-300)', borderRadius: 'var(--radius-md)', background: 'var(--paper-0)', padding: 20 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 24 }}>Admin Dashboard</h1>
        <p style={{ color: 'var(--ink-700)', fontSize: 14 }}>
          Look up an account reference to see every customer request, plus the audit/log details for selected conversations.
        </p>

        <div style={{ display: 'grid', gap: 10, marginTop: 16 }}>
          <input
            value={accountRef}
            onChange={(e) => setAccountRef(e.target.value)}
            placeholder="Account reference"
            style={{ padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--line-300)' }}
          />
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={searchRequests}
              style={{ flex: 1, padding: '10px 14px', borderRadius: 'var(--radius-sm)', border: 'none', background: 'var(--ink-900)', color: 'var(--paper-0)' }}
            >
              Search Account
            </button>
            <button
              onClick={loadEscalations}
              style={{ flex: 1, padding: '10px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--ink-900)', background: 'transparent', color: 'var(--ink-900)' }}
            >
              All Escalations
            </button>
          </div>
        </div>

        <div style={{ marginTop: 20, fontSize: 13, color: 'var(--ink-700)', minHeight: 22 }}>{status}</div>
        {error && <div style={{ color: 'var(--alert-600)', marginTop: 8 }}>{error}</div>}

        <div style={{ marginTop: 18, maxHeight: 'calc(100vh - 280px)', overflowY: 'auto' }}>
          {(requests.length > 0 ? requests : escalationTickets).map((request) => (
            <button
              key={request.conversation_id}
              onClick={() => showTranscript(request.conversation_id)}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '12px 14px',
                borderRadius: 'var(--radius-sm)',
                border: selectedConversation === request.conversation_id ? '1px solid var(--ink-900)' : '1px solid var(--line-300)',
                background: selectedConversation === request.conversation_id ? 'var(--paper-100)' : 'transparent',
                marginBottom: 10,
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{request.conversation_id}</div>
                  <div style={{ color: 'var(--ink-600)', fontSize: 12 }}>{request.status}</div>
                </div>
                <div style={{ textAlign: 'right', fontSize: 11, color: 'var(--ink-700)' }}>
                  {request.started_at.split('T')[0]}
                </div>
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--ink-700)' }}>
                Outcome: {request.outcome || 'pending'}
              </div>
            </button>
          ))}
        </div>
      </section>

      <section style={{ border: '1px solid var(--line-300)', borderRadius: 'var(--radius-md)', background: 'var(--paper-0)', padding: 20, overflowY: 'auto' }}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20 }}>Conversation transcript</h2>
        {transcript ? (
          <div style={{ marginTop: 16 }}>
            <div style={{ marginBottom: 18, fontSize: 14, color: 'var(--ink-700)' }}>
              Account: {transcript.customer_ref} · Started: {transcript.started_at} · Status: {transcript.status}
            </div>
            <div style={{ marginBottom: 18 }}>
              <strong>Audit trail:</strong> {auditTrail ? `${auditTrail.events.length} events, chain ${auditTrail.chain_intact ? 'verified' : 'failed'}` : 'Loading...'}
            </div>
            <div style={{ display: 'grid', gap: 14 }}>
              {transcript.messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  style={{ padding: '12px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--line-300)', background: message.role === 'customer' ? 'var(--paper-100)' : 'var(--paper-0)' }}
                >
                  <div style={{ fontSize: 11, color: 'var(--ink-700)', marginBottom: 6 }}>
                    {message.role} · {message.created_at}
                  </div>
                  <div style={{ fontSize: 14, color: 'var(--ink-900)' }}>{message.content}</div>
                  {message.intent && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--trust-700)' }}>Intent: {message.intent}</div>}
                </div>
              ))}
            </div>
            {convData?.status === 'awaiting_human_review' && (
              <div style={{ marginTop: 20, padding: 16, background: 'var(--paper-100)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--line-300)' }}>
                <h5>Admin Decision Required</h5>
                <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                  <button
                    onClick={() => handleResolve('approved')}
                    disabled={resolving}
                    style={{ background: 'var(--success-600)', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer' }}
                  >
                    Accept
                  </button>
                  <button
                    onClick={() => handleResolve('denied')}
                    disabled={resolving}
                    style={{ background: 'var(--alert-600)', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer' }}
                  >
                    Decline
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div style={{ marginTop: 16, color: 'var(--ink-700)', fontSize: 13 }}>
            Select a request on the left to inspect the full transcript and see whether the admin approved it.
          </div>
        )}
      </section>
    </div>
  )
}
