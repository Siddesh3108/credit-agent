import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'
import ConfirmActionModal from './ConfirmActionModal'
import EscalationBanner from './EscalationBanner'
import { useConversation } from '../hooks/useConversation'

export default function ChatWindow({ conversationId, token }) {
  const { messages, pendingConfirmation, escalation, sending, error, sendMessage, confirmAction } =
    useConversation(conversationId, token)
  const [draft, setDraft] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pendingConfirmation])

  function handleSubmit(e) {
    e.preventDefault()
    if (!draft.trim() || sending) return
    sendMessage(draft.trim())
    setDraft('')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
        {messages.length === 0 && (
          <div style={{ color: 'var(--ink-700)', fontSize: 14, lineHeight: 1.6 }}>
            <p>Try: "please waive my late fee", "my card was stolen", or "can you raise my credit limit".</p>
            <p>
              When the agent asks a follow-up question, answer with the requested info in plain text, for example:
              <strong> "late fee from last week"</strong>, <strong>"stolen card"</strong>, or <strong>"increase to 8000"</strong>.
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} index={i} conversationId={conversationId} />
        ))}
        <EscalationBanner escalation={escalation} />
        {error && (
          <div style={{ color: 'var(--alert-600)', fontSize: 13, marginTop: 8 }}>{error}</div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        style={{
          display: 'flex',
          gap: 8,
          padding: '12px 20px',
          borderTop: '1px solid var(--line-300)',
          background: 'var(--paper-0)',
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a message…"
          disabled={sending || Boolean(pendingConfirmation)}
          style={{
            flex: 1,
            padding: '10px 12px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--line-300)',
          }}
        />
        <button
          type="submit"
          disabled={sending || Boolean(pendingConfirmation)}
          style={{
            padding: '10px 18px',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            background: 'var(--ink-900)',
            color: 'var(--paper-0)',
            fontWeight: 600,
            opacity: sending || pendingConfirmation ? 0.5 : 1,
          }}
        >
          Send
        </button>
      </form>

      <ConfirmActionModal pending={pendingConfirmation} onConfirm={confirmAction} busy={sending} />
    </div>
  )
}
