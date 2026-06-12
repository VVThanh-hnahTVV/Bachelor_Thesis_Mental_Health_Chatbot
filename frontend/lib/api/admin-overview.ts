import { getAuthToken } from "@/lib/auth-token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface DayStat {
  date: string;
  label: string;
  messages: number;
  active_sessions: number;
}

export interface RecentConversation {
  session_id: string;
  title: string;
  user_label: string;
  updated_at: string | null;
}

export interface KnowledgeStaging {
  pending: number;
  approved: number;
  rejected: number;
  indexed: number;
}

export interface AdminOverviewStats {
  total_users: number;
  users_this_month: number;
  user_growth_pct: number | null;
  total_conversations: number;
  total_messages: number;
  messages_today: number;
  conversations_today: number;
  messages_by_day: DayStat[];
  wellness_completions_today: number;
  wellness_completions_total: number;
  avg_wellness_rating: number | null;
  total_wellness_ratings: number;
  recent_conversations: RecentConversation[];
  knowledge_staging: KnowledgeStaging;
  knowledge_staging_health_pct: number;
  updated_at: string;
}

async function adminFetch(path: string) {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  if (!res.ok) {
    let message = "Request failed";
    try {
      const data = await res.json();
      message = data.detail || message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return res.json();
}

export async function getAdminOverview(
  days = 7
): Promise<AdminOverviewStats> {
  return adminFetch(`/api/v1/admin/overview?days=${days}`);
}
