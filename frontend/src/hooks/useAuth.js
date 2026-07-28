import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '../services/apiClient'

const STORAGE_KEYS = {
  customerRef: 'cardservicing_customer_ref',
  conversationId: 'cardservicing_conversation_id',
  token: 'cardservicing_token',
  role: 'cardservicing_role',
}

/**
 * Reference-implementation session hook. Real deployments authenticate
 * the customer via the OIDC session established before the chat even
 * loads (§3.1) -- this hook's `login` call stands in for "the customer is
 * already signed in and the BFF exchanges that session for a
 * conversation-scoped token." See app/core/security.py's module
 * docstring on the backend side for the same caveat.
 */
export function useAuth() {
  const [customerRef, setCustomerRef] = useState(null)
  const [conversationId, setConversationId] = useState(null)
  const [token, setToken] = useState(null)
  const [role, setRole] = useState('customer')
  const [error, setError] = useState(null)

  useEffect(() => {
    const storedCustomerRef = window.localStorage.getItem(STORAGE_KEYS.customerRef)
    const storedConversationId = window.localStorage.getItem(STORAGE_KEYS.conversationId)
    const storedToken = window.localStorage.getItem(STORAGE_KEYS.token)
    const storedRole = window.localStorage.getItem(STORAGE_KEYS.role)

    if (storedToken) {
      setCustomerRef(storedCustomerRef)
      setConversationId(storedConversationId)
      setToken(storedToken)
      setRole(storedRole || 'customer')
    }
  }, [])

  const persist = (newCustomerRef, newConversationId, newToken, newRole) => {
    if (newToken) {
      window.localStorage.setItem(STORAGE_KEYS.customerRef, newCustomerRef ?? '')
      window.localStorage.setItem(STORAGE_KEYS.conversationId, newConversationId ?? '')
      window.localStorage.setItem(STORAGE_KEYS.token, newToken)
      window.localStorage.setItem(STORAGE_KEYS.role, newRole)
    }
  }

  const clearPersisted = () => {
    window.localStorage.removeItem(STORAGE_KEYS.customerRef)
    window.localStorage.removeItem(STORAGE_KEYS.conversationId)
    window.localStorage.removeItem(STORAGE_KEYS.token)
    window.localStorage.removeItem(STORAGE_KEYS.role)
  }

  const login = useCallback(async (ref, requestedRole = 'customer', adminSecret) => {
    setError(null)
    try {
      if (requestedRole === 'customer') {
        await apiClient.createAccount(ref).catch(() => undefined)
        const { conversation_id, session_token } = await apiClient.startConversation(ref)
        setCustomerRef(ref)
        setConversationId(conversation_id)
        setToken(session_token)
        setRole('customer')
        persist(ref, conversation_id, session_token, 'customer')
      } else {
        const { session_token } = await apiClient.login(ref, 'admin', adminSecret)
        setCustomerRef(ref)
        setConversationId(null)
        setToken(session_token)
        setRole('admin')
        persist(ref, null, session_token, 'admin')
      }
    } catch (e) {
      setError(e.message)
    }
  }, [])

  const logout = useCallback(() => {
    setCustomerRef(null)
    setConversationId(null)
    setToken(null)
    setRole('customer')
    setError(null)
    clearPersisted()
  }, [])

  return { customerRef, conversationId, token, role, error, login, logout, isAuthenticated: Boolean(token) }
}
