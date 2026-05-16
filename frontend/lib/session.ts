const SESSION_STORAGE_KEY = "mh_session_id";

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
