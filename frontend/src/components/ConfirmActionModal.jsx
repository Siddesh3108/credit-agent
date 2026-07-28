/**
 * §15: "Any node that reaches confirm_with_user renders a distinct,
 * unambiguous confirmation UI... the system never executes a financial
 * action from an inferred 'yes' buried in free text." This is that UI --
 * a real modal with explicit Confirm/Cancel buttons, never a chat message
 * the user could ambiguously reply to.
 */
export default function ConfirmActionModal({ pending, onConfirm, onCancel, busy }) {
  if (!pending) return null
  const { intent, decision_summary } = pending.interrupt_payload || {}

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(24,32,36,0.35)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10,
      }}
    >
      <div
        style={{
          background: 'var(--paper-0)',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-card)',
          padding: 24,
          width: 360,
          border: '1px solid var(--line-300)',
        }}
      >
        <h2 id="confirm-title" style={{ fontFamily: 'var(--font-display)', fontSize: 20, margin: '0 0 8px' }}>
          Confirm this action
        </h2>
        <p style={{ margin: '0 0 4px', color: 'var(--ink-700)' }}>
          {intent ? intent.replace(/_/g, ' ') : 'This request'} is ready to go through.
        </p>
        {decision_summary?.reason_codes?.length > 0 && (
          <p className="mono" style={{ fontSize: 12, color: 'var(--ink-700)' }}>
            {decision_summary.reason_codes.join(' · ')}
          </p>
        )}
        <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
          <button
            onClick={() => onConfirm(true)}
            disabled={busy}
            style={{
              flex: 1,
              padding: '10px 0',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              background: 'var(--trust-700)',
              color: 'white',
              fontWeight: 600,
            }}
          >
            Confirm
          </button>
          <button
            onClick={() => onConfirm(false)}
            disabled={busy}
            style={{
              flex: 1,
              padding: '10px 0',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--line-300)',
              background: 'transparent',
              color: 'var(--ink-900)',
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
