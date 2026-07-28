import { useState } from 'react'
import { apiClient } from '../services/apiClient'

const STATUS_STYLE = {
  approved: { label: 'Approved', bg: 'var(--trust-50)', fg: 'var(--trust-700)' },
  resolved: { label: 'Approved', bg: 'var(--trust-50)', fg: 'var(--trust-700)' },
  denied: { label: 'Denied', bg: 'var(--alert-50)', fg: 'var(--alert-600)' },
  manual_review: { label: 'Manual review', bg: 'var(--review-50)', fg: 'var(--review-700)' },
  awaiting_confirmation: { label: 'Awaiting your confirmation', bg: 'var(--review-50)', fg: 'var(--review-700)' },
  awaiting_human_review: { label: 'With a specialist', bg: 'var(--review-50)', fg: 'var(--review-700)' },
  escalated: { label: 'With a specialist', bg: 'var(--review-50)', fg: 'var(--review-700)' },
}

function statusFor(result) {
  return (
    STATUS_STYLE[result.decision?.outcome] ||
    STATUS_STYLE[result.status] || { label: result.status, bg: 'var(--paper-100)', fg: 'var(--ink-700)' }
  )
}

/**
 * The signature element: every financial decision renders as its own
 * ledger card, with an on-demand link to the *real* hash-chained audit
 * trail (fetched from GET /v1/audit/{id}) -- not a decorative fake hash.
 * Showing a plausible-looking-but-fabricated hash string here would risk
 * a real user believing they're looking at genuine cryptographic proof
 * when they aren't; this only ever displays hashes the backend actually
 * computed and verified.
 */
export default function LedgerEntry({ result, index, conversationId }) {
  const status = statusFor(result)
  const seq = String(index).padStart(4, '0')
  const [trail, setTrail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)

  async function toggleTrail() {
    if (expanded) {
      setExpanded(false)
      return
    }
    setExpanded(true)
    if (!trail) {
      setLoading(true)
      try {
        const data = await apiClient.getAuditTrail(conversationId)
        setTrail(data)
      } catch {
        setTrail({ error: true })
      } finally {
        setLoading(false)
      }
    }
  }

  return (
    <div
      style={{
        border: '1px solid var(--line-300)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--paper-0)',
        boxShadow: 'var(--shadow-card)',
        padding: '14px 16px',
        maxWidth: 420,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span className="mono" style={{ fontSize: 12, color: 'var(--ink-700)' }}>
          No. {seq}
        </span>
        <span
          className="mono"
          style={{
            fontSize: 11,
            fontWeight: 500,
            padding: '2px 8px',
            borderRadius: 999,
            background: status.bg,
            color: status.fg,
          }}
        >
          {status.label}
        </span>
      </div>

      <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, marginTop: 6 }}>
        {result.intent ? result.intent.replace(/_/g, ' ') : 'Request update'}
      </div>

      {result.decision?.reason_codes?.length > 0 && (
        <div className="mono" style={{ fontSize: 11, color: 'var(--ink-700)', marginTop: 4 }}>
          {result.decision.reason_codes.join(' · ')}
        </div>
      )}

      <button
        onClick={toggleTrail}
        className="mono"
        style={{
          fontSize: 11,
          color: 'var(--ink-700)',
          marginTop: 10,
          paddingTop: 8,
          borderTop: '1px dashed var(--line-300)',
          width: '100%',
          textAlign: 'left',
          background: 'none',
          border: 'none',
          borderTopStyle: 'dashed',
          borderTopWidth: 1,
          borderTopColor: 'var(--line-300)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span aria-hidden="true">⛓</span>
        {expanded ? 'Hide' : 'View'} verified audit trail
      </button>

      {expanded && (
        <div style={{ marginTop: 8, fontSize: 11 }} className="mono">
          {loading && <div>Checking the hash chain…</div>}
          {trail?.error && <div style={{ color: 'var(--alert-600)' }}>Couldn't load the audit trail.</div>}
          {trail && !trail.error && (
            <>
              <div style={{ color: trail.chain_intact ? 'var(--trust-700)' : 'var(--alert-600)' }}>
                Chain {trail.chain_intact ? 'verified intact' : 'INTEGRITY FAILURE'} ·{' '}
                {trail.events.length} events
              </div>
              <div style={{ maxHeight: 140, overflowY: 'auto', marginTop: 6 }}>
                {trail.events.map((e) => (
                  <div key={e.event_id} style={{ display: 'flex', gap: 8, padding: '2px 0' }}>
                    <span style={{ color: 'var(--ink-700)', minWidth: 24 }}>#{e.sequence_no}</span>
                    <span style={{ minWidth: 140 }}>{e.event_type}</span>
                    <span style={{ color: 'var(--ink-700)' }}>{e.event_hash.slice(0, 12)}…</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
