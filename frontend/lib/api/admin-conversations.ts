import { getAuthToken } from "@/lib/auth-token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type ConversationOwnerFilter = "registered" | "guest";

export interface AdminConversationUser {
  id: string;
  name: string;
  email: string;
}

export interface AdminConversation {
  session_id: string;
  conversation_id: string;
  title: string;
  chat_mode: string;
  summary: string | null;
  summary_updated_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
  user: AdminConversationUser | null;
}

export interface AdminConversationsListResponse {
  conversations: AdminConversation[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ConversationDayStat {
  date: string;
  label: string;
  messages: number;
  active_sessions: number;
  new_sessions: number;
}

export interface ConversationStats {
  total_conversations: number;
  total_messages: number;
  conversations_today: number;
  messages_today: number;
  registered_sessions: number;
  guest_sessions: number;
  unique_users_with_sessions: number;
  with_summary: number;
  avg_messages_per_conversation: number;
  messages_by_day: ConversationDayStat[];
  updated_at: string;
}

async function adminFetch(path: string, init?: RequestInit) {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
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
  if (res.status === 204) return null;
  return res.json();
}

export async function getConversationStats(
  days = 7
): Promise<ConversationStats> {
  return adminFetch(`/api/v1/admin/conversations/stats?days=${days}`);
}

export async function listAdminConversations(params?: {
  page?: number;
  page_size?: number;
  search?: string;
  owner?: ConversationOwnerFilter | "";
}): Promise<AdminConversationsListResponse> {
  const q = new URLSearchParams();
  if (params?.page) q.set("page", String(params.page));
  if (params?.page_size) q.set("page_size", String(params.page_size));
  if (params?.search) q.set("search", params.search);
  if (params?.owner) q.set("owner", params.owner);
  const qs = q.toString();
  return adminFetch(`/api/v1/admin/conversations${qs ? `?${qs}` : ""}`);
}
