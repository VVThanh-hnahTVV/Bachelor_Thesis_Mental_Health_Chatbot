import { getOrCreateSessionId } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface DashboardStats {
  mood_score: number | null;
  mood_source: "chat" | "form" | "none";
  dominant_emotion: string | null;
  emotion_samples_today: number;
  completion_rate: number;
  therapy_sessions: number;
  total_activities_today: number;
  chat_turns_today: number;
  last_updated: string;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const sessionId = getOrCreateSessionId();
  const q = new URLSearchParams({ session_id: sessionId });
  const response = await fetch(`${API_BASE}/api/v1/dashboard/stats?${q.toString()}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch dashboard stats");
  }
  return response.json();
}
