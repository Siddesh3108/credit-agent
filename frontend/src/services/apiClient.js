const BASE = "/v1";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export function authHeader(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export const apiClient = {
  login(customerRef, role = "customer", adminSecret) {
    const body = { customer_ref: customerRef, role };
    if (role === "admin") {
      body.admin_secret = adminSecret;
    }
    return request("/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  startConversation(customerRef) {
    return request("/conversations", {
      method: "POST",
      body: JSON.stringify({ customer_ref: customerRef }),
    });
  },

  createAccount(customerRef) {
    return request("/dev/accounts", {
      method: "POST",
      body: JSON.stringify({ account_ref: customerRef }),
    });
  },

  getAccountRequests(accountRef, token) {
    return request(`/conversations/account/${accountRef}/requests`, {
      method: "GET",
      headers: authHeader(token),
    });
  },

  getConversationTranscript(conversationId, token) {
    return request(`/conversations/${conversationId}/transcript`, {
      method: "GET",
      headers: authHeader(token),
    });
  },

  sendMessage(conversationId, token, message) {
    return request(`/conversations/${conversationId}/messages`, {
      method: "POST",
      headers: authHeader(token),
      body: JSON.stringify({ message }),
    });
  },

  resumeConfirm(conversationId, token, confirmed) {
    return request(`/conversations/${conversationId}/resume`, {
      method: "POST",
      headers: authHeader(token),
      body: JSON.stringify({ kind: "confirm", confirmed }),
    });
  },

  adminResolve(conversationId, token, outcome, note = "reviewed by admin") {
    return request(`/conversations/${conversationId}/resume`, {
      method: "POST",
      headers: authHeader(token),
      body: JSON.stringify({ kind: "human_decision", outcome, agent_id: "admin", note }),
    });
  },

  getConversation(conversationId, token) {
    return request(`/conversations/${conversationId}`, {
      headers: authHeader(token),
    });
  },

  getEscalations(token) {
    return request(`/escalations`, {
      headers: authHeader(token),
    });
  },

  getAuditTrail(conversationId) {
    return request(`/audit/${conversationId}`);
  },
};
