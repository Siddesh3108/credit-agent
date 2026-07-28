import LedgerEntry from './LedgerEntry'

export default function MessageBubble({ message, index, conversationId }) {
  if (message.role === 'customer') {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', margin: '8px 0' }}>
        <div
          style={{
            background: 'var(--ink-900)',
            color: 'var(--paper-0)',
            padding: '10px 14px',
            borderRadius: '14px 14px 4px 14px',
            maxWidth: 420,
          }}
        >
          {message.text}
        </div>
      </div>
    )
  }

  // Agent turn: if it carried a real decision/outcome, show the ledger
  // card (the signature element); otherwise just a plain reply bubble
  // (e.g. a clarifying question has no decision to show yet).
  const result = message.result
  const hasDecision = result?.decision || result?.status === 'escalated' || result?.status === 'awaiting_human_review'

  return (
    <div style={{ display: 'flex', justifyContent: 'flex-start', margin: '8px 0' }}>
      {hasDecision ? (
        <LedgerEntry result={result} index={index} conversationId={conversationId} />
      ) : (
        <div
          style={{
            background: 'var(--paper-100)',
            padding: '10px 14px',
            borderRadius: '14px 14px 14px 4px',
            maxWidth: 420,
          }}
        >
          {result?.message ? result.message :
            result?.escalation_reason
            ? "I need to check on something before I can continue -- one moment."
            : 'Could you tell me a bit more about what you need?'}
        </div>
      )}
    </div>
  )
}
