import { getAuthToken } from "@/lib/auth-token";
import { getKnownChatSessionIds, getOrCreateSessionId } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type ChatMode = "psychologist" | "medical";

export function chatModeStorageKey(sessionId: string): string {
  return `chat_mode:${sessionId}`;
}

export interface QuickReply {
  id: string;
  label: string;
  message: string;
}

export interface CrisisChoice {
  id: string;
  label: string;
}

export type CrisisStage =
  | "none"
  | "concern"
  | "confirm"
  | "sos"
  | "human_escalation"
  | "overwhelm"
  | "overwhelm_doing"
  | "overwhelm_check"
  | "overwhelm_not_better"
  | "safety_watch"
  | "someone_else"
  | "someone_else_followup"
  | "recovery";

export const CRISIS_CHIP_PREFIX = "__crisis_id__:";

const CRISIS_CHIP_LABELS_VI: Record<string, string> = {
  // Legacy / SOS
  "crisis:share_more": "Điều gì đang làm mình đau nhất",
  "crisis:breathing_light": "Hướng dẫn mình hít thở chậm",
  "crisis:ack_safety_concern": "Giúp mình kiểm tra mình có an toàn",
  "crisis:confirm_self_harm": "Có, mình đang nghĩ tự làm hại",
  "crisis:deny_self_harm": "Không, chỉ buồn thôi",
  "crisis:talk_to_someone": "Mình muốn nói với người thân",
  "crisis:breathing": "Tôi muốn thử bài tập hít thở",
  "crisis:ocean": "Cho tôi nghe âm sóng thư giãn",
  "crisis:hotline": "Tôi muốn xem số điện thoại hỗ trợ",
  "crisis:feel_safer": "Tôi cảm thấy đỡ hơn một chút rồi",
  "crisis:return_chat": "Quay lại trò chuyện bình thường",
  // Triage
  "crisis:need_more_help": "Có, tôi cần thêm giúp đỡ",
  "crisis:just_overwhelmed": "Không, tôi chỉ đang quá tải",
  "crisis:misunderstood": "Bạn hiểu sai rồi",
  "crisis:someone_else": "Đây là về người khác",
  // Human escalation
  "crisis:show_emergency": "Xem số liên hệ khẩn cấp",
  "crisis:help_message_someone": "Giúp tôi nhắn tin cho người thân",
  "crisis:i_am_safe_now": "Tôi đang an toàn rồi",
  // Overwhelm activity choice
  "crisis:slow_breathing": "Hít thở chậm",
  "crisis:calming_music": "Nhạc thư giãn",
  "crisis:grounding_exercise": "Bài tập hiện diện",
  // During / after activity
  "crisis:done_activity": "Tôi đã làm xong",
  "crisis:feel_better_yes": "Có, tôi cảm thấy đỡ hơn",
  "crisis:feel_better_no": "Chưa, vẫn còn nặng nề",
  // Not-better options
  "crisis:not_better_need_help": "Có, tôi cần thêm hỗ trợ",
  "crisis:try_another": "Thử hoạt động khác",
  "crisis:not_better_back_to_chat": "Quay lại trò chuyện",
  // Recovery
  "crisis:back_to_conversation": "Quay lại trò chuyện",
  "crisis:end_for_now": "Kết thúc phiên hôm nay",
  // Safety-watch
  "crisis:sw_back_to_chat": "Quay lại trò chuyện",
  "crisis:explain_more": "Cho tôi giải thích thêm",
  // Someone-else triage
  "crisis:they_in_danger": "Họ có thể đang gặp nguy hiểm",
  "crisis:they_safe_struggling": "Họ ổn nhưng đang khó khăn",
  "crisis:they_not_sure": "Tôi không chắc",
  "crisis:back_to_chat": "Tôi hiểu, cảm ơn bạn",
};

const CRISIS_CHIP_LABELS_EN: Record<string, string> = {
  // Legacy / SOS
  "crisis:share_more": "What's hurting most right now",
  "crisis:breathing_light": "Guide me through slow breathing",
  "crisis:ack_safety_concern": "Help me check I'm safe",
  "crisis:confirm_self_harm": "Yes, I'm thinking of hurting myself",
  "crisis:deny_self_harm": "No, I'm just very sad",
  "crisis:talk_to_someone": "I want to talk to someone I trust",
  "crisis:breathing": "I want to try a breathing exercise",
  "crisis:ocean": "Play calming ocean sounds",
  "crisis:hotline": "Show me support numbers",
  "crisis:feel_safer": "I feel a little safer now",
  "crisis:return_chat": "Return to normal conversation",
  // Triage
  "crisis:need_more_help": "Yes, I need more help",
  "crisis:just_overwhelmed": "No, just feeling overwhelmed",
  "crisis:misunderstood": "You misunderstood",
  "crisis:someone_else": "It's someone else",
  // Human escalation
  "crisis:show_emergency": "Show emergency contacts",
  "crisis:help_message_someone": "Help me message someone I trust",
  "crisis:i_am_safe_now": "I am safe now",
  // Overwhelm activity choice
  "crisis:slow_breathing": "Slow breathing",
  "crisis:calming_music": "Calming music",
  "crisis:grounding_exercise": "Grounding exercise",
  // During / after activity
  "crisis:done_activity": "Done, check how I feel",
  "crisis:feel_better_yes": "Yes, I feel better",
  "crisis:feel_better_no": "Not really",
  // Not-better options
  "crisis:not_better_need_help": "Yes, I need more help",
  "crisis:try_another": "Try another calming exercise",
  "crisis:not_better_back_to_chat": "Back to conversation",
  // Recovery
  "crisis:back_to_conversation": "Back to conversation",
  "crisis:end_for_now": "End for now",
  // Safety-watch
  "crisis:sw_back_to_chat": "Back to conversation",
  "crisis:explain_more": "Let me explain what I meant",
  // Someone-else triage
  "crisis:they_in_danger": "They might be in danger now",
  "crisis:they_safe_struggling": "They are safe but struggling",
  "crisis:they_not_sure": "I'm not sure",
  "crisis:back_to_chat": "Understood, thank you",
};

function chipLabelFallback(chipId: string): string {
  return (
    CRISIS_CHIP_LABELS_EN[chipId] ??
    CRISIS_CHIP_LABELS_VI[chipId] ??
    chipId
  );
}

/** Show chip label in bubbles instead of crisis_id / __crisis_id__ payload. */
export function formatMessageForDisplay(content: string): string {
  const text = content.trim();
  for (const prefix of [CRISIS_CHIP_PREFIX, "crisis_id:", "__crisis_id:"]) {
    if (text.startsWith(prefix)) {
      const id = text.slice(prefix.length).trim();
      return chipLabelFallback(id);
    }
  }
  if (text.startsWith("crisis:")) {
    return chipLabelFallback(text);
  }
  return content;
}

export function normalizeCrisisChoices(raw: unknown): CrisisChoice[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((item, i) => {
    if (typeof item === "string") {
      return { id: `legacy:${i}`, label: item };
    }
    if (item && typeof item === "object" && "label" in item) {
      const o = item as { id?: string; label?: string };
      return {
        id: String(o.id ?? `legacy:${i}`),
        label: String(o.label ?? ""),
      };
    }
    return { id: `legacy:${i}`, label: String(item) };
  }).filter((c) => c.label.length > 0);
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
    message_type?: "normal" | "off_topic" | "crisis" | "medical";
    chat_blocked?: boolean;
    crisis_stage?: CrisisStage;
    crisis_choices?: CrisisChoice[] | string[];
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
    pending_activity_rating?: {
      activity_id: string;
      completion_id: string;
      rated?: boolean;
      rating?: number;
    };
    prompt_screening?: string | null;
    retrieval_mode?: "vector" | "lexical" | "hybrid" | "none";
    retrieved_chunks?: Array<{
      id: string;
      topic: string;
      score: number;
      source: string;
    }>;
    safety_fallback_used?: boolean;
    chat_mode?: ChatMode;
    agent_name?: string;
    [key: string]: unknown;
  };
}

export interface ChatSession {
  sessionId: string;
  title?: string;
  messages: ChatMessage[];
  createdAt: Date;
  updatedAt: Date;
  chatMode?: ChatMode;
}

export interface ApiResponse {
  message: string;
  response?: string;
  assistant_message_id?: string;
  // Safety / routing
  chat_blocked?: boolean;
  crisis_stage?: CrisisStage;
  crisis_choices?: CrisisChoice[];
  message_type?: "normal" | "off_topic" | "crisis" | "medical";
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

function mapStreamDoneToApiResponse(data: Record<string, unknown>): ApiResponse {
  return {
    message: String(data.reply ?? ""),
    response: String(data.reply ?? ""),
    assistant_message_id: (data.assistant_message_id as string) ?? undefined,
    chat_blocked: Boolean(data.chat_blocked),
    crisis_stage: (data.crisis_stage ?? "none") as CrisisStage,
    crisis_choices: normalizeCrisisChoices(data.crisis_choices),
    message_type: (data.message_type as ApiResponse["message_type"]) ?? "normal",
    emotion: (data.emotion as string) ?? undefined,
    therapy_strategy: (data.therapy_strategy as string) ?? undefined,
    quick_replies: (data.quick_replies as QuickReply[]) ?? [],
    metadata: {
      ...((data.metadata as ChatMessage["metadata"]) || {}),
      crisis_stage: data.crisis_stage,
      crisis_choices: normalizeCrisisChoices(data.crisis_choices),
      quick_replies: data.quick_replies,
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
  chatMode: ChatMode = "psychologist",
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
      chat_mode: chatMode,
    }),
  });

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
  chatMode: ChatMode = "psychologist",
  onStatus?: (label: string, step: string) => void
): Promise<ApiResponse> => {
  try {
    return await sendChatMessageStream(sessionId, message, chatMode, onStatus);
  } catch (streamErr) {
    console.warn("Chat stream unavailable, using standard API:", streamErr);
    return sendChatMessage(sessionId, message, chatMode);
  }
};

export const sendChatMessage = async (
  sessionId: string,
  message: string,
  chatMode: ChatMode = "psychologist"
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
      chat_mode: chatMode,
    }),
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
    crisis_stage: (data.crisis_stage ?? data.metadata?.crisis_stage ?? "none") as CrisisStage,
    crisis_choices: normalizeCrisisChoices(
      data.crisis_choices ?? data.metadata?.crisis_choices
    ),
    message_type: data.message_type ?? "normal",
    emotion: data.emotion ?? undefined,
    therapy_strategy: data.therapy_strategy ?? undefined,
    quick_replies: data.quick_replies ?? [],
    metadata: {
      ...(data.metadata || {}),
      crisis_stage: data.crisis_stage ?? data.metadata?.crisis_stage,
      crisis_choices: normalizeCrisisChoices(
        data.crisis_choices ?? data.metadata?.crisis_choices
      ),
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
    content: formatMessageForDisplay(String(msg.content ?? "")),
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
    messages: [],
    createdAt: new Date(session.updated_at),
    updatedAt: new Date(session.updated_at),
    chatMode: (session.chat_mode as ChatMode) || "psychologist",
  }));
};
