import AuthGate from './components/AuthGate'
import AdminDashboard from './components/AdminDashboard'
import ChatWindow from './components/ChatWindow'
import { useAuth } from './hooks/useAuth'

export default function App() {
  const { customerRef, conversationId, token, role, error, login, logout, isAuthenticated } = useAuth()

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header
        style={{
          padding: '14px 20px',
          borderBottom: '1px solid var(--line-300)',
          background: 'var(--paper-0)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 18 }}>Card Servicing</span>
        {isAuthenticated && (
          <button
            onClick={logout}
            style={{
              padding: '8px 14px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--line-300)',
              background: 'transparent',
              cursor: 'pointer',
            }}
          >
            Sign out
          </button>
        )}
      </header>

      <main style={{ flex: 1, overflow: 'hidden' }}>
        {isAuthenticated ? (
          role === 'admin' ? (
            <AdminDashboard token={token} />
          ) : (
            <ChatWindow customerRef={customerRef} conversationId={conversationId} token={token} />
          )
        ) : (
          <AuthGate onLogin={login} error={error} />
        )}
      </main>
    </div>
  )
}
