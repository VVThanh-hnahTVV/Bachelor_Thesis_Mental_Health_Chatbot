interface ActivityEntry {
  type: string;
  name: string;
  description?: string;
  duration?: number;
}

import { getOrCreateSessionId } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function mapActivityId(type: string): "breathing_box" | "ocean_sound" {
  const normalized = type.toLowerCase();
  if (normalized.includes("breath") || normalized.includes("meditation")) {
    return "breathing_box";
  }
  return "ocean_sound";
}

export async function logActivity(
  data: ActivityEntry
): Promise<{ success: boolean; data: any }> {
  const response = await fetch(`${API_BASE}/api/v1/activities/complete`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: getOrCreateSessionId(),
      activity_id: mapActivityId(data.type),
      duration_sec: data.duration ? data.duration * 60 : undefined,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || "Failed to log activity");
  }

  return { success: true, data: await response.json() };
}
