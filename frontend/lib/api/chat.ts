import { getOrCreateSessionId } from "@/lib/session";
import { getAuthToken } from "@/lib/auth-token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface QuickReply {
  id: string;
  label: string;
  message: string;
}

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  metadata?: {
    technique?: string;
    goal?: string;
    progress?: any[];
    // Safety / routing
    message_type?: "normal" | "off_topic" | "crisis";
    chat_blocked?: boolean;
    crisis_choices?: string[];
    // Emotion / therapy
    emotion?: string;
    therapy_strategy?: string;
    // Wellness activities
    suggested_activities?: Array<{
      id: string;
      title: string;
      description: string;
    }>;
    quick_replies?: QuickReply[];
    show_micro_feedback?: boolean;
    prompt_screening?: string | null;
    retrieval_mode?: "vector" | "lexical" | "hybrid" | "none";
    retrieved_chunks?: Array<{
      id: string;
      topic: string;
      score: number;
      source: string;
    }>;
    safety_fallback_used?: boolean;
    [key: string]: unknown;
  };
}

export interface ChatSession {
  sessionId: string;
  messages: ChatMessage[];
  createdAt: Date;
  updatedAt: Date;
}

export interface ApiResponse {
  message: string;
  response?: string;
  assistant_message_id?: string;
  // Safety / routing
  chat_blocked?: boolean;
  crisis_choices?: string[];
  message_type?: "normal" | "off_topic" | "crisis";
  // Emotion / therapy
  emotion?: string;
  therapy_strategy?: string;
  quick_replies?: QuickReply[];
  metadata?: ChatMessage["metadata"];
}

export async function submitMessageFeedback(
  sessionId: string,
  assistantMessageId: string,
  value: "yes" | "a_bit" | "no"
): Promise<void> {
  const token = getAuthToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}/api/v1/chat/feedback`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      session_id: sessionId,
      assistant_message_id: assistantMessageId,
      value,
    }),
  });
  if (!response.ok) {
    throw new Error("Failed to submit feedback");
  }
}

export const createChatSession = async (): Promise<string> => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};

export const sendChatMessage = async (
  sessionId: string,
  message: string
): Promise<ApiResponse> => {
  const token = getAuthToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}/api/v1/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to send message");
  }
  const data = await response.json();
  return {
    message: data.reply,
    response: data.reply,
    assistant_message_id: data.assistant_message_id ?? undefined,
    chat_blocked: data.chat_blocked ?? false,
    crisis_choices: data.crisis_choices ?? [],
    message_type: data.message_type ?? "normal",
    emotion: data.emotion ?? undefined,
    therapy_strategy: data.therapy_strategy ?? undefined,
    quick_replies: data.quick_replies ?? [],
    metadata: {
      ...(data.metadata || {}),
      quick_replies: data.quick_replies ?? data.metadata?.quick_replies,
      show_micro_feedback: data.metadata?.show_micro_feedback,
      prompt_screening: data.metadata?.prompt_screening,
    },
  };
};

export const getChatHistory = async (
  sessionId: string
): Promise<ChatMessage[]> => {
  const q = new URLSearchParams({ session_id: sessionId });
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}/api/v1/messages?${q.toString()}`, {
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch chat history");
  }
  const data = await response.json();
  if (!Array.isArray(data)) return [];
  return data.map((msg: any) => ({
    id: msg.id,
    role: msg.role,
    content: msg.content,
    timestamp: new Date(msg.created_at),
    metadata: msg.metadata,
  }));
};

export const getAllChatSessions = async (): Promise<ChatSession[]> => {
  const sessionId = getOrCreateSessionId();
  const q = new URLSearchParams({ session_id: sessionId });
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}/api/v1/conversations?${q.toString()}`, {
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch chat sessions");
  }
  const data = await response.json();
  if (!Array.isArray(data)) return [];
  return data.map((session: any) => ({
    sessionId: String(session.session_id),
    messages: [],
    createdAt: new Date(session.updated_at),
    updatedAt: new Date(session.updated_at),
  }));
};
