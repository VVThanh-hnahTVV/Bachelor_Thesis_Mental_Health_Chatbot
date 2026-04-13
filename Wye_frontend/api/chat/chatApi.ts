import { apiGet, apiPost } from "../apiMethod";

export type ChatSession = {
  _id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string | null;
};

export type ChatMessage = {
  _id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type CreateSessionRequest = {
  title?: string;
};

type CreateMessageRequest = {
  content: string;
  role?: "user" | "assistant";
};

export const getChatSessions = () => apiGet<ChatSession[]>("/chat/sessions");

export const createChatSession = (payload?: CreateSessionRequest) =>
  apiPost<ChatSession, CreateSessionRequest>("/chat/sessions", payload ?? { title: "New conversation" });

export const getChatMessages = (sessionId: string) =>
  apiGet<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`);

export const createChatMessage = (sessionId: string, payload: CreateMessageRequest) =>
  apiPost<ChatMessage, CreateMessageRequest>(`/chat/sessions/${sessionId}/messages`, payload);
