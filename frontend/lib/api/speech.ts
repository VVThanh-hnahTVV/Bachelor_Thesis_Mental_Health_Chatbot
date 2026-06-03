import { getAuthToken } from "@/lib/auth-token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface TranscribeSpeechResult {
  text: string;
  language_code?: string | null;
}

export async function transcribeSpeech(
  audio: Blob,
  languageCode?: string
): Promise<TranscribeSpeechResult> {
  const form = new FormData();
  const ext = audio.type.includes("mp4")
    ? "mp4"
    : audio.type.includes("ogg")
      ? "ogg"
      : "webm";
  form.append("audio", audio, `recording.${ext}`);
  if (languageCode) {
    form.append("language_code", languageCode);
  }

  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}/api/v1/speech/transcribe`, {
    method: "POST",
    headers,
    body: form,
  });

  if (!response.ok) {
    let detail = "Failed to transcribe audio";
    try {
      const payload = await response.json();
      detail =
        typeof payload.detail === "string"
          ? payload.detail
          : JSON.stringify(payload.detail ?? payload);
    } catch {
      detail = (await response.text()) || detail;
    }
    throw new Error(detail);
  }

  return response.json();
}
