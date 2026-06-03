const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface ScreeningQuestions {
  instrument: string;
  questions: string[];
  options: string[];
  disclaimer: string;
}

export interface ScreeningResult {
  instrument: string;
  score: number;
  interpretation: string;
  disclaimer: string;
  created_at: string;
}

export async function fetchScreeningQuestions(
  instrument: "phq2" | "phq4" = "phq2"
): Promise<ScreeningQuestions> {
  const q = new URLSearchParams({ instrument, lang: "en" });
  const response = await fetch(`${API_BASE}/api/v1/screening/questions?${q}`);
  if (!response.ok) throw new Error("Failed to load screening questions");
  return response.json();
}

export async function submitScreening(
  sessionId: string,
  instrument: "phq2" | "phq4",
  answers: number[]
): Promise<ScreeningResult> {
  const response = await fetch(`${API_BASE}/api/v1/screening`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      instrument,
      answers,
      lang: "en",
    }),
  });
  if (!response.ok) throw new Error("Failed to submit screening");
  return response.json();
}

export async function getLatestScreening(
  sessionId: string
): Promise<ScreeningResult | null> {
  const q = new URLSearchParams({ session_id: sessionId });
  const response = await fetch(`${API_BASE}/api/v1/screening/latest?${q}`);
  if (response.status === 404 || !response.ok) return null;
  return response.json();
}
