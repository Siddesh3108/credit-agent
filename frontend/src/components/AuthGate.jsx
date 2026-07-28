import { useState } from 'react'

/**
 * Reference-implementation stand-in for real OIDC session establishment
 * (§3.1) -- see useAuth.js's docstring. In production this component
 * wouldn't exist in this form at all; the chat would simply load inside
 * an already-authenticated session.
 */
export default function AuthGate({ onLogin, error }) {
  const [ref, setRef] = useState('')
  const [role, setRole] = useState('customer')
  const [adminSecret, setAdminSecret] = useState('')

  return (
    <div style={{ maxWidth: 420, margin: '80px auto', textAlign: 'center' }}>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 24 }}>Card Servicing</h1>
      <p style={{ color: 'var(--ink-700)', fontSize: 14, marginBottom: 16 }}>
        Select a role and sign in. Customers can start a chat by entering an account reference.
        Admins can review pending decisions and approve or deny escalations.
      </p>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 16 }}>
        <button
          type="button"
          onClick={() => setRole('customer')}
          style={{
            padding: '10px 16px',
            borderRadius: 'var(--radius-sm)',
            border: role === 'customer' ? '2px solid var(--ink-900)' : '1px solid var(--line-300)',
            background: role === 'customer' ? 'var(--ink-900)' : 'transparent',
            color: role === 'customer' ? 'var(--paper-0)' : 'var(--ink-900)',
            cursor: 'pointer',
          }}
        >
          Customer
        </button>
        <button
          type="button"
          onClick={() => setRole('admin')}
          style={{
            padding: '10px 16px',
            borderRadius: 'var(--radius-sm)',
            border: role === 'admin' ? '2px solid var(--ink-900)' : '1px solid var(--line-300)',
            background: role === 'admin' ? 'var(--ink-900)' : 'transparent',
            color: role === 'admin' ? 'var(--paper-0)' : 'var(--ink-900)',
            cursor: 'pointer',
          }}
        >
          Admin
        </button>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (ref.trim()) onLogin(ref.trim(), role, adminSecret.trim())
        }}
        style={{ display: 'grid', gap: 12 }}
      >
        <input
          value={ref}
          onChange={(e) => setRef(e.target.value)}
          placeholder={role === 'customer' ? 'Enter account reference' : 'Enter admin identifier'}
          style={{
            padding: '10px 12px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--line-300)',
            fontFamily: 'var(--font-mono)',
          }}
        />
        {role === 'admin' && (
          <input
            value={adminSecret}
            onChange={(e) => setAdminSecret(e.target.value)}
            placeholder="Admin secret"
            type="password"
            style={{
              padding: '10px 12px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--line-300)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        )}
        <button
          type="submit"
          style={{
            padding: '10px 16px',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            background: 'var(--ink-900)',
            color: 'var(--paper-0)',
            fontWeight: 600,
          }}
        >
          {role === 'customer' ? 'Start chat' : 'Sign in as admin'}
        </button>
      </form>
      {error && <p style={{ color: 'var(--alert-600)', fontSize: 13 }}>{error}</p>}
    </div>
  )
}
