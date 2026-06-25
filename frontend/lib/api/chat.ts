import { getAuthToken } from "@/lib/auth-token";
import { getKnownChatSessionIds, getOrCreateSessionId } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant" | "support" | "system";
  content: string;
  timestamp: Date;
  metadata?: {
    message_type?: "normal" | "off_topic" | "medical" | string;
    sender_name?: string;
    visibility?: string;
    suggested_activities?: Array<{
      id: string;
      title: string;
      description: string;
    }>;
    pending_activity_rating?: {
      activity_id: string;
      completion_id: string;
      rated?: boolean;
      rating?: number;
    };
    retrieval_mode?: "vector" | "lexical" | "hybrid" | "none";
    retrieved_chunks?: Array<{
      id: string;
      topic: string;
      score: number;
      source: string;
    }>;
    safety_fallback_used?: boolean;
    agent_name?: string;
    image_url?: string;
    rating_thanks?: string;
    [key: string]: unknown;
  };
}

export interface ChatSession {
  sessionId: string;
  title?: string;
  summary?: string;
  messages: ChatMessage[];
  createdAt: Date;
  updatedAt: Date;
  chatMode?: "medical";
}

export interface ApiResponse {
  message: string;
  response?: string;
  assistant_message_id?: string;
  message_type?: "normal" | "off_topic" | "medical";
  metadata?: ChatMessage["metadata"];
  support_mode?: string;
  assigned_support_name?: string | null;
}

export class RateLimitError extends Error {
  code = "DAILY_CHAT_LIMIT_EXCEEDED";
  used?: number;
  limit?: number;
  remaining?: number;
  resetsAt?: string;

  constructor(detail: {
    message?: string;
    used?: number;
    limit?: number;
    remaining?: number;
    resets_at?: string;
  }) {
    super(detail.message || "Bạn đã đạt giới hạn câu hỏi hôm nay.");
    this.name = "RateLimitError";
    this.used = detail.used;
    this.limit = detail.limit;
    this.remaining = detail.remaining;
    this.resetsAt = detail.resets_at;
  }
}

/** Build a RateLimitError from a 429 response body ({ detail: {...} }). */
async function rateLimitErrorFromResponse(
  response: Response
): Promise<RateLimitError> {
  try {
    const data = await response.json();
    const detail = data?.detail ?? data ?? {};
    return new RateLimitError(detail);
  } catch {
    return new RateLimitError({});
  }
}

export const createChatSession = async (): Promise<string> => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};

function mapStreamDoneToApiResponse(data: Record<string, unknown>): ApiResponse {
  return {
    message: String(data.reply ?? ""),
    response: String(data.reply ?? ""),
    assistant_message_id: (data.assistant_message_id as string) ?? undefined,
    message_type: (data.message_type as ApiResponse["message_type"]) ?? "normal",
    support_mode: data.support_mode as string | undefined,
    assigned_support_name: data.assigned_support_name as string | null | undefined,
    metadata: {
      ...((data.metadata as ChatMessage["metadata"]) || {}),
      suggested_activities:
        (data.suggested_activities as Array<{
          id: string;
          title: string;
          description: string;
        }>) ?? (data.metadata as ChatMessage["metadata"])?.suggested_activities,
    },
  };
}

type StreamPayload = {
  type: string;
  label?: string;
  step?: string;
  message?: string;
  [key: string]: unknown;
};

function consumeSseBuffer(
  buffer: string,
  onEvent: (payload: StreamPayload) => void,
  flushAll = false
): string {
  const parts = buffer.split("\n\n");
  const remainder = flushAll ? "" : (parts.pop() ?? "");

  for (const part of parts) {
    const line = part.split("\n").find((l) => l.startsWith("data: "));
    if (!line) continue;
    try {
      onEvent(JSON.parse(line.slice(6)) as StreamPayload);
    } catch {
      // ignore malformed chunks
    }
  }

  if (flushAll && remainder.trim()) {
    const line = remainder.split("\n").find((l) => l.startsWith("data: "));
    if (line) {
      try {
        onEvent(JSON.parse(line.slice(6)) as StreamPayload);
      } catch {
        // ignore
      }
    }
    return "";
  }

  return remainder;
}

/** Stream status steps via SSE, then return the final chat response. */
export const sendChatMessageStream = async (
  sessionId: string,
  message: string,
  onStatus?: (label: string, step: string) => void
): Promise<ApiResponse> => {
  const token = getAuthToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}/api/v1/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      message,
      session_id: sessionId,
    }),
  });

  if (response.status === 429) {
    throw await rateLimitErrorFromResponse(response);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to send message");
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Streaming not supported");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: ApiResponse | null = null;

  const handlePayload = (payload: StreamPayload) => {
    if (payload.type === "status" && payload.label) {
      onStatus?.(payload.label, String(payload.step ?? ""));
    } else if (payload.type === "done") {
      finalResponse = mapStreamDoneToApiResponse(payload);
    } else if (payload.type === "error") {
      throw new Error(payload.message || "Chat stream failed");
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
    }
    buffer = consumeSseBuffer(buffer, handlePayload, done);
    if (done) break;
  }

  if (!finalResponse) {
    throw new Error("No response received from stream");
  }
  return finalResponse;
};

/** Prefer streaming status; fall back to standard POST if stream fails. */
export const sendChatMessageWithStatus = async (
  sessionId: string,
  message: string,
  onStatus?: (label: string, step: string) => void
): Promise<ApiResponse> => {
  try {
    return await sendChatMessageStream(sessionId, message, onStatus);
  } catch (streamErr) {
    if (streamErr instanceof RateLimitError) {
      throw streamErr;
    }
    console.error("Chat stream failed, using standard API:", streamErr);
    onStatus?.("Đang xử lý yêu cầu", "fallback");
    return sendChatMessage(sessionId, message);
  }
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
    body: JSON.stringify({
      message,
      session_id: sessionId,
    }),
  });
  if (response.status === 429) {
    throw await rateLimitErrorFromResponse(response);
  }
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to send message");
  }
  const data = await response.json();
  return {
    message: data.reply,
    response: data.reply,
    assistant_message_id: data.assistant_message_id ?? undefined,
    message_type: data.message_type ?? "normal",
    support_mode: data.support_mode,
    assigned_support_name: data.assigned_support_name,
    metadata: {
      ...(data.metadata || {}),
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
    content: String(msg.content ?? ""),
    timestamp: new Date(msg.created_at),
    metadata: msg.metadata,
  }));
};

export async function deleteChatSession(sessionId: string): Promise<void> {
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(
    `${API_BASE}/api/v1/conversations/${encodeURIComponent(sessionId)}`,
    { method: "DELETE", headers }
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to delete chat session");
  }
}

export const getAllChatSessions = async (): Promise<ChatSession[]> => {
  const token = getAuthToken();
  const knownIds = getKnownChatSessionIds();
  const params = new URLSearchParams({ limit: "50" });
  if (knownIds.length > 0) {
    params.set("session_ids", knownIds.join(","));
  } else if (!token) {
    params.set("session_id", getOrCreateSessionId());
  }
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}/api/v1/conversations?${params.toString()}`, {
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
    title: session.title ? String(session.title) : undefined,
    summary: session.summary ? String(session.summary) : undefined,
    messages: [],
    createdAt: new Date(session.updated_at),
    updatedAt: new Date(session.updated_at),
    chatMode: "medical",
  }));
};
