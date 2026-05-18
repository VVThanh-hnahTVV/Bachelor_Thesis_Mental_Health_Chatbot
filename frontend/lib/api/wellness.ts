const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function startWellnessSession(
  sessionId: string,
  activityId: "breathing_box" | "ocean_sound"
): Promise<{ reply: string; assistant_message_id?: string }> {
  const response = await fetch(`${API_BASE}/api/v1/wellness/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, activity_id: activityId }),
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

export async function completeWellnessSession(sessionId: string): Promise<{
  checkin_message: string;
  show_micro_feedback: boolean;
}> {
  const response = await fetch(`${API_BASE}/api/v1/wellness/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!response.ok) {
    throw new Error("Failed to complete wellness session");
  }
  return response.json();
}
