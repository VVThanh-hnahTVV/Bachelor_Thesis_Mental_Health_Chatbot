const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type SupportMode = "ai" | "awaiting_support" | "human" | "closed";

export interface ConversationStatus {
  session_id: string;
  support_mode: SupportMode;
  assigned_support_name: string | null;
  assigned_support_id: string | null;
}

export interface HandoffResponse {
  reply: string;
  session_id: string;
  conversation_id: string;
  assistant_message_id?: string | null;
  support_mode: SupportMode;
  assigned_support_name?: string | null;
  metadata?: Record<string, unknown>;
}

export async function getConversationStatus(
  sessionId: string
): Promise<ConversationStatus> {
  const res = await fetch(
    `${API_BASE}/api/v1/conversations/${encodeURIComponent(sessionId)}/status`,
    { cache: "no-store" }
  );
  if (!res.ok) {
    return { session_id: sessionId, support_mode: "ai", assigned_support_name: null, assigned_support_id: null };
  }
  return res.json();
}

export async function requestHandoff(sessionId: string): Promise<HandoffResponse> {
  const res = await fetch(`${API_BASE}/api/v1/handoff/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Handoff request failed");
  }
  return res.json();
}

export function wsBaseUrl(): string {
  return API_BASE.replace(/^http/, "ws");
}

export function buildChatWsUrl(
  sessionId: string,
  role: "user" | "support",
  token?: string | null
): string {
  const q = new URLSearchParams({
    session_id: sessionId,
    role,
  });
  if (token) q.set("token", token);
  return `${wsBaseUrl()}/api/v1/ws/chat?${q.toString()}`;
}
