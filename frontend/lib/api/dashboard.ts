import { getAuthToken } from "@/lib/auth-token";
import { getOrCreateSessionId } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface DashboardStats {
  completion_rate: number;
  therapy_sessions: number;
  total_activities_today: number;
  chat_turns_today: number;
  last_updated: string;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const sessionId = getOrCreateSessionId();
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const now = new Date();
  const dayStart = new Date(now);
  dayStart.setHours(0, 0, 0, 0);

  let activitiesToday = 0;
  try {
    const q = new URLSearchParams({ session_id: sessionId, limit: "100" });
    const res = await fetch(`${API_BASE}/api/v1/activities?${q}`, {
      headers,
      cache: "no-store",
    });
    if (res.ok) {
      const rows = await res.json();
      if (Array.isArray(rows)) {
        for (const row of rows) {
          const created = row?.created_at ? new Date(String(row.created_at)) : null;
          if (created && created >= dayStart) activitiesToday += 1;
        }
      }
    }
  } catch {
    // ignore
  }

  let sessions = 0;
  try {
    const q = new URLSearchParams({ session_id: sessionId, limit: "50" });
    const res = await fetch(`${API_BASE}/api/v1/conversations?${q}`, { headers, cache: "no-store" });
    if (res.ok) {
      const rows = await res.json();
      if (Array.isArray(rows)) sessions = rows.length;
    }
  } catch {
    // ignore
  }

  const engaged = activitiesToday > 0 || sessions > 0;

  return {
    completion_rate: engaged ? 100 : 0,
    therapy_sessions: sessions,
    total_activities_today: activitiesToday,
    chat_turns_today: 0,
    last_updated: now.toISOString(),
  };
}
