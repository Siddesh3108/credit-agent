import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '../services/apiClient'

/**
 * Drives one conversation's turn-by-turn state against the backend. Each
 * backend response's `status` maps directly to what the UI needs to show
 * next: "awaiting_confirmation" -> render ConfirmActionModal,
 * "awaiting_human_review" -> render EscalationBanner, "resolved" /
 * "escalated" -> append a ledger entry summarizing the outcome.
 */
export function useConversation(conversationId, token) {
  const [messages, setMessages] = useState([])
  const [pendingConfirmation, setPendingConfirmation] = useState(null)
  const [escalation, setEscalation] = useState(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!conversationId || !token) {
      return
    }

    let cancelled = false
    const loadTranscript = async () => {
      try {
        const transcript = await apiClient.getConversationTranscript(conversationId, token)
        if (cancelled) return
        const restored = transcript.messages.map((message) => {
          if (message.role === 'customer') {
            return { role: 'customer', text: message.content }
          }
          return { role: 'agent', result: { status: 'resolved', intent: message.intent, decision: null, escalation_reason: null, message: message.content } }
        })
        setMessages(restored)
      } catch {
        // ignore; fresh conversation may not have transcript yet
      }
    }

    loadTranscript()
    return () => {
      cancelled = true
    }
  }, [conversationId, token])

  const applyResult = useCallback((result) => {
    if (result.status === 'awaiting_confirmation') {
      setPendingConfirmation(result)
    } else {
      setPendingConfirmation(null)
    }
    if (result.status === 'awaiting_human_review' || result.status === 'escalated') {
      setEscalation(result)
    } else if (result.status === 'resolved') {
      setEscalation(null)
    }
    setMessages((prev) => [...prev, { role: 'agent', result }])
  }, [])

  const sendMessage = useCallback(
    async (text) => {
      setError(null)
      setSending(true)
      setMessages((prev) => [...prev, { role: 'customer', text }])
      try {
        const result = await apiClient.sendMessage(conversationId, token, text)
        applyResult(result)
      } catch (e) {
        setError(e.message)
      } finally {
        setSending(false)
      }
    },
    [conversationId, token, applyResult],
  )

  const confirmAction = useCallback(
    async (confirmed) => {
      setError(null)
      setSending(true)
      try {
        const result = await apiClient.resumeConfirm(conversationId, token, confirmed)
        applyResult(result)
      } catch (e) {
        setError(e.message)
      } finally {
        setSending(false)
      }
    },
    [conversationId, token, applyResult],
  )

  return { messages, pendingConfirmation, escalation, sending, error, sendMessage, confirmAction }
}
