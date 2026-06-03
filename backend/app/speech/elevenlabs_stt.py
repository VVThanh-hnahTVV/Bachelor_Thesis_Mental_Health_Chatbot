from __future__ import annotations

import httpx

ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB


class SpeechToTextError(Exception):
    pass


async def transcribe_with_elevenlabs(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    api_key: str,
    model_id: str = "scribe_v2",
    language_code: str | None = None,
) -> dict[str, str | None]:
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise SpeechToTextError("Audio file is too large (max 10 MB)")

    data: dict[str, str] = {"model_id": model_id}
    if language_code:
        data["language_code"] = language_code

    files = {"file": (filename, audio_bytes, content_type or "application/octet-stream")}

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            ELEVENLABS_STT_URL,
            headers={"xi-api-key": api_key},
            data=data,
            files=files,
        )

    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise SpeechToTextError(f"ElevenLabs STT failed ({response.status_code}): {detail}")

    payload = response.json()
    text = str(payload.get("text") or "").strip()
    if not text:
        raise SpeechToTextError("No speech detected in the recording")

    language = payload.get("language_code")
    return {
        "text": text,
        "language_code": str(language) if language else None,
    }
