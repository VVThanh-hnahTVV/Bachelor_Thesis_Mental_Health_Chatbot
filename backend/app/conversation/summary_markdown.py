"""Markdown-formatted conversation summaries (AI rolling, handoff brief, human session)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName, get_settings
from app.llm.factory import default_provider, get_chat_model, invoke_with_fallback

AI_ROLLING_SYSTEM = """\
You maintain a concise rolling summary of a chat session between a user and Helios (AI medical assistant).

Given the previous summary and a transcript of the turns since it was written
(one or more user/assistant exchanges), produce an UPDATED summary in Markdown with these sections:

## Chủ đề chính
(1-3 sentences)

## Triệu chứng / mối quan tâm
- bullet list (omit section if none)

## Bối cảnh quan trọng
- bullet list

## Hành động / gợi ý đã đưa
- bullet list

Rules:
- Merge new facts from this turn; drop redundant details
- Use the same language as the user when possible (Vietnamese or English)
- Output Markdown only — no code fences wrapping the whole document
- Keep total length under ~12 sentences across sections
"""

HANDOFF_BRIEF_SYSTEM = """\
You prepare a handoff brief for a human support counselor joining a Helios chat session.

Given the user's long-term context (prior sessions), AI conversation summary for this session,
and full transcript, write a Markdown brief for the counselor:

## Bối cảnh từ các phiên trước
- bullets from long-term memory, or "Không có" if none provided

## Tóm tắt nhanh
(2-4 sentences about THIS session)

## Mối quan tâm chính của người dùng
- bullets

## Lịch sử trao đổi quan trọng
- key points from transcript

## Rủi ro / dấu hiệu cần lưu ý
- bullets (write "Không phát hiện" if none)

## Gợi ý cho chuyên viên
- suggested opening / follow-up questions

Use the user's language when possible. Output Markdown only.
Do NOT include personally identifiable information (email, phone, address).
"""

HUMAN_SESSION_SYSTEM = """\
You summarize a human support session between a user and a counselor (after AI handoff).

Given the transcript of support-user messages only, write a Markdown summary:

## Tóm tắt phiên hỗ trợ
(2-4 sentences)

## Nội dung trao đổi chính
- bullets

## Cam kết / bước tiếp theo
- bullets (if any)

## Ghi chú cho hồ sơ
- optional admin notes

Use the user's language when possible. Output Markdown only.
"""

MERGED_SUMMARY_SYSTEM = """\
You maintain ONE consolidated Markdown summary of an entire chat session that may include:
- Phase 1: user ↔ Helios (AI assistant)
- Phase 2: user ↔ human counselor (if present)

Given the existing session summary and the human support transcript, produce a single updated summary:

## Chủ đề / mối quan tâm chính

## Diễn biến cuộc trò chuyện
- Highlights from AI phase (from existing summary)
- Highlights from human support phase (from transcript)

## Hành động / gợi ý / cam kết

## Ghi chú quan trọng

Rules:
- Merge into one coherent document; remove duplication
- Clearly distinguish AI vs human support when both occurred
- Same language as the user when possible
- Markdown only — no outer code fences
- Keep concise but complete (~15 sentences max)
"""

USER_LONG_TERM_MEMORY_SYSTEM = """\
You maintain a concise long-term memory profile for a mental-health chat user across multiple sessions.

Given the previous long-term memory and new session information, produce an UPDATED Markdown profile:

## Bối cảnh / hồ sơ tâm lý
(1-3 sentences)

## Chủ đề đã thảo luận qua các phiên
- bullet list

## Triệu chứng / mối quan tâm lặp lại
- bullet list (omit section if none)

## Can thiện / gợi ý đã từng đưa
- bullet list

Rules:
- Merge new facts from the session update; drop redundant or outdated details
- Keep ONLY mental-health-related context — no PII (email, phone, address, full names)
- Use the same language as the user when possible (Vietnamese or English)
- Output Markdown only — no code fences wrapping the whole document
- Keep total length under ~20 sentences across sections
"""


def _format_transcript(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for doc in messages:
        role = str(doc.get("role") or "unknown")
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        sender = str(meta.get("sender_name") or role)
        content = str(doc.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"[{sender}] {content}")
    return "\n".join(lines) if lines else "(no messages)"


async def _invoke_summary(
    *,
    system: str,
    human: str,
    provider: ProviderName | None = None,
    label: str,
) -> str:
    prov = provider or default_provider()
    max_tokens = get_settings().conversation_summary_max_tokens
    llm = get_chat_model(prov)
    msg = await invoke_with_fallback(
        llm,
        [SystemMessage(content=system), HumanMessage(content=human)],
        primary=prov,
        label=label,
        max_tokens=max_tokens,
    )
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    return text.strip()


async def generate_ai_rolling_summary(
    *,
    previous_summary: str,
    user_message: str,
    assistant_reply: str,
    provider: ProviderName | None = None,
) -> str:
    prev = (previous_summary or "").strip() or "(none yet)"
    human = (
        f"Previous summary:\n{prev}\n\n"
        f"Latest user message:\n{user_message.strip()}\n\n"
        f"Latest assistant reply:\n{assistant_reply.strip()}\n\n"
        "Updated Markdown summary:"
    )
    return await _invoke_summary(
        system=AI_ROLLING_SYSTEM,
        human=human,
        provider=provider,
        label="conversation_summary.markdown",
    )


async def generate_ai_rolling_summary_batch(
    *,
    previous_summary: str,
    transcript_messages: list[dict[str, Any]],
    provider: ProviderName | None = None,
) -> str:
    """Fold several un-summarized turns into the rolling summary in one call."""
    prev = (previous_summary or "").strip() or "(none yet)"
    transcript = _format_transcript(transcript_messages)
    human = (
        f"Previous summary:\n{prev}\n\n"
        f"Turns since the previous summary:\n{transcript}\n\n"
        "Updated Markdown summary:"
    )
    return await _invoke_summary(
        system=AI_ROLLING_SYSTEM,
        human=human,
        provider=provider,
        label="conversation_summary.markdown_batch",
    )


async def generate_handoff_brief(
    *,
    ai_summary: str,
    transcript_messages: list[dict[str, Any]],
    user_long_term_memory: str = "",
    provider: ProviderName | None = None,
) -> str:
    transcript = _format_transcript(transcript_messages)
    ltm = (user_long_term_memory or "").strip() or "(none — guest or first session)"
    human = (
        f"User long-term memory (prior sessions):\n{ltm}\n\n"
        f"AI rolling summary (this session):\n{(ai_summary or '').strip() or '(none)'}\n\n"
        f"Full transcript:\n{transcript}\n\n"
        "Handoff brief:"
    )
    return await _invoke_summary(
        system=HANDOFF_BRIEF_SYSTEM,
        human=human,
        provider=provider,
        label="handoff_brief.markdown",
    )


async def generate_human_session_summary(
    *,
    human_messages: list[dict[str, Any]],
    provider: ProviderName | None = None,
) -> str:
    transcript = _format_transcript(human_messages)
    human = f"Support session transcript:\n{transcript}\n\nMarkdown summary:"
    return await _invoke_summary(
        system=HUMAN_SESSION_SYSTEM,
        human=human,
        provider=provider,
        label="human_session_summary.markdown",
    )


async def generate_merged_conversation_summary(
    *,
    previous_summary: str,
    human_messages: list[dict[str, Any]],
    provider: ProviderName | None = None,
) -> str:
    transcript = _format_transcript(human_messages)
    prev = (previous_summary or "").strip() or "(none yet)"
    human = (
        f"Existing session summary:\n{prev}\n\n"
        f"Human support transcript:\n{transcript}\n\n"
        "Updated consolidated Markdown summary:"
    )
    return await _invoke_summary(
        system=MERGED_SUMMARY_SYSTEM,
        human=human,
        provider=provider,
        label="conversation_summary.merged",
    )


async def generate_user_long_term_memory_update(
    *,
    previous_memory: str,
    session_summary: str,
    source: str = "ai_turn",
    provider: ProviderName | None = None,
) -> str:
    prev = (previous_memory or "").strip() or "(none yet)"
    summary = (session_summary or "").strip()
    if not summary:
        return prev if prev != "(none yet)" else ""
    human = (
        f"Previous long-term memory:\n{prev}\n\n"
        f"New session information (source={source}):\n{summary}\n\n"
        "Updated long-term memory profile:"
    )
    return await _invoke_summary(
        system=USER_LONG_TERM_MEMORY_SYSTEM,
        human=human,
        provider=provider,
        label="user_long_term_memory.markdown",
    )
