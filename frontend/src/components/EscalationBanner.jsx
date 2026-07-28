/**
 * §15: "Escalation banner makes the handoff visible and reassuring...
 * rather than feeling like a dead end." Deliberately not styled as an
 * error/alert -- it's on the amber "review" tokens, not the red "alert"
 * ones, and the copy tells the customer their context carries over
 * (§11.3's "no need to repeat yourself" property).
 */
export default function EscalationBanner({ escalation }) {
  if (!escalation) return null

  const isPendingReview = escalation.status === 'awaiting_human_review'

  return (
    <div
      style={{
        background: 'var(--review-50)',
        border: '1px solid var(--review-700)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 16px',
        margin: '12px 0',
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
      }}
    >
      <span aria-hidden="true" style={{ fontSize: 18 }}>
        ◆
      </span>
      <div>
        <div style={{ fontWeight: 600, color: 'var(--review-700)' }}>
          {isPendingReview ? "You're being connected to a specialist" : 'A specialist will follow up'}
        </div>
        <div style={{ fontSize: 13, color: 'var(--ink-700)', marginTop: 2 }}>
          They'll already have the details from this conversation -- you won't need to start over
          or verify your identity again.
        </div>
      </div>
    </div>
  )
}
