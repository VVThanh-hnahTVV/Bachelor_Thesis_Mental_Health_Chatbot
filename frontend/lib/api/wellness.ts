const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type VideoSourceCredit = {
  name: string;
  url?: string | null;
  license?: string | null;
  attribution?: string | null;
};

export type WellnessActivity = {
  id: string;
  title: string;
  description: string;
  content_type: "interactive" | "video" | string;
  activity_type: string;
  ui_component: string;
  video_url?: string | null;
  youtube_id?: string | null;
  video_source?: VideoSourceCredit | null;
  duration_min: number;
  avg_rating: number;
  rating_count: number;
  benefits?: string[];
  tags?: string[];
};

export async function getActivityCatalog(
  scope: string = "helios",
  lang: "vi" | "en" = "vi"
): Promise<WellnessActivity[]> {
  const params = new URLSearchParams({ scope, lang });
  const response = await fetch(`${API_BASE}/api/v1/activities/catalog?${params}`);
  if (!response.ok) {
    throw new Error("Failed to load activity catalog");
  }
  return response.json();
}

export async function startWellnessSession(
  sessionId: string,
  activityId: string,
  options?: { quiet?: boolean; lang?: "vi" | "en"; chatMode?: "psychologist" | "medical" }
): Promise<{ reply: string; assistant_message_id?: string }> {
  const response = await fetch(`${API_BASE}/api/v1/wellness/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      activity_id: activityId,
      quiet: options?.quiet ?? false,
      lang: options?.lang,
      chat_mode: options?.chatMode,
    }),
  });
  if (!response.ok) {
    throw new Error("Failed to start wellness session");
  }
  const data = await response.json();
  return {
    reply: data.reply,
    assistant_message_id: data.assistant_message_id,
  };
}

export async function completeWellnessSession(
  sessionId: string,
  options?: {
    lang?: "vi" | "en";
    activityId?: string;
    durationSec?: number;
  }
): Promise<{
  checkin_message: string;
  show_micro_feedback: boolean;
  show_activity_rating: boolean;
  activity_id?: string | null;
  completion_id?: string | null;
  assistant_message_id?: string | null;
}> {
  const response = await fetch(`${API_BASE}/api/v1/wellness/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      lang: options?.lang,
      activity_id: options?.activityId,
      duration_sec: options?.durationSec,
    }),
  });
  if (!response.ok) {
    throw new Error("Failed to complete wellness session");
  }
  return response.json();
}

export async function rateActivity(
  sessionId: string,
  activityId: string,
  completionId: string,
  rating: number,
  chatMode?: "psychologist" | "medical",
  messageId?: string
): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE}/api/v1/activities/rate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      activity_id: activityId,
      completion_id: completionId,
      rating,
      chat_mode: chatMode,
      message_id: messageId,
    }),
  });
  if (!response.ok) {
    throw new Error("Failed to submit rating");
  }
  return response.json();
}
