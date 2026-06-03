const SESSION_STORAGE_KEY = "mh_session_id";
const CHAT_SESSIONS_STORAGE_KEY = "mh_chat_session_ids";
const MAX_STORED_CHAT_SESSIONS = 50;

function generateSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return generateSessionId();
  const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;
  const created = generateSessionId();
  window.localStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
}

export function newSession(): string {
  const created = generateSessionId();
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SESSION_STORAGE_KEY, created);
  }
  return created;
}

export function registerChatSessionId(sessionId: string): void {
  if (typeof window === "undefined" || !sessionId.trim()) return;
  const existing = getKnownChatSessionIds();
  const next = [
    sessionId,
    ...existing.filter((id) => id !== sessionId),
  ].slice(0, MAX_STORED_CHAT_SESSIONS);
  window.localStorage.setItem(CHAT_SESSIONS_STORAGE_KEY, JSON.stringify(next));
}

export function getKnownChatSessionIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(CHAT_SESSIONS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((id): id is string => typeof id === "string" && id.length > 0);
  } catch {
    return [];
  }
}

export function unregisterChatSessionId(sessionId: string): void {
  if (typeof window === "undefined" || !sessionId.trim()) return;
  const next = getKnownChatSessionIds().filter((id) => id !== sessionId);
  window.localStorage.setItem(CHAT_SESSIONS_STORAGE_KEY, JSON.stringify(next));
}
