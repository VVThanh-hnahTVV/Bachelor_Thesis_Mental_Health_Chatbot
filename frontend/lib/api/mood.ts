import { getOrCreateSessionId } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface MoodEntry {
  score: number;
  note?: string;
}

interface MoodStats {
  average: number;
  count: number;
  highest: number;
  lowest: number;
  history: Array<{
    _id: string;
    score: number;
    note?: string;
    timestamp: string;
  }>;
}

export async function trackMood(
  data: MoodEntry
): Promise<{ success: boolean; data: any }> {
  const normalizedScore = Math.max(1, Math.min(10, Math.round(data.score / 10)));
  const response = await fetch(`${API_BASE}/api/v1/mood`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: getOrCreateSessionId(),
      score: normalizedScore,
      note: data.note ?? null,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || "Failed to track mood");
  }

  return { success: true, data: await response.json() };
}

export async function getMoodHistory(params?: {
  startDate?: string;
  endDate?: string;
  limit?: number;
}): Promise<{ success: boolean; data: any[] }> {
  const queryParams = new URLSearchParams();
  if (params?.limit) queryParams.append("limit", params.limit.toString());
  queryParams.append("session_id", getOrCreateSessionId());

  const response = await fetch(`${API_BASE}/api/v1/mood?${queryParams.toString()}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || "Failed to fetch mood history");
  }

  return { success: true, data: await response.json() };
}

export async function getMoodStats(
  _period: "week" | "month" | "year" = "week"
): Promise<{
  success: boolean;
  data: MoodStats;
}> {
  const { data } = await getMoodHistory();
  const values = data.map((item: any) => Number(item.score)).filter((v) => !Number.isNaN(v));
  const average = values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : 0;
  return {
    success: true,
    data: {
      average,
      count: values.length,
      highest: values.length ? Math.max(...values) : 0,
      lowest: values.length ? Math.min(...values) : 0,
      history: data.map((item: any) => ({
        _id: item.id,
        score: Number(item.score),
        note: item.note ?? undefined,
        timestamp: item.created_at,
      })),
    },
  };
}
