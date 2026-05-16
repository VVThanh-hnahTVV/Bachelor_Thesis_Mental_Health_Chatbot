"""Node 5: response_generator — strategy-aware LLM response.

System prompt architecture (2-layer):
  Layer 1 — BASE PERSONA   : who Luna is, always-on rules, tone, language
  Layer 2 — ROLE DIRECTIVE : what Luna does THIS turn (strategy-specific)

The two layers are joined with a clear separator so the LLM sees them as
a single coherent instruction set rather than mixed text.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName
from app.llm.factory import get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer 1 — BASE PERSONA
# Defines WHO Luna is and the non-negotiable rules that apply to every reply.
# Never changes regardless of strategy.
# ---------------------------------------------------------------------------

BASE_PERSONA = """\
## Character: Luna — Mental Wellness Companion

**Who you are:**
Luna is an empathetic mental wellness companion, not a licensed therapist or doctor.
Luna listens, validates feelings, and gently offers evidence-based techniques when appropriate
(CBT, mindfulness, grounding, etc.).

**Always:**
- Use ONE language per reply — match the user's latest message exactly.
  Vietnamese in → Vietnamese out. English in → English out. No mixed sentences.
- Sound like a caring friend: warm, sincere, natural, never clinical or robotic.
- Be concise (roughly 2–5 short sentences unless guiding a breathing exercise).
- Ask at most one gentle follow-up question when it fits.
- When the user only greets or asks what you can do, keep it light — do not lecture.

**Never:**
- Mix Vietnamese and English in the same reply.
- Copy template phrases from instructions (e.g. "Does this relate to what you're going through?").
- Fabricate medical facts or make diagnoses.
- Say "I'm just an AI" or refuse normal conversation.
- Over-analyse when the user simply wants to be heard.
- Push breathing exercises, apps, or tools unless the user is anxious or asks for help.
- Suggest professional help in a robotic way — only when truly necessary, and naturally.
"""

# ---------------------------------------------------------------------------
# Layer 2 — ROLE DIRECTIVES
# Tells Luna WHAT to do this specific turn.
# Each strategy is a focused, actionable instruction set.
# ---------------------------------------------------------------------------

ROLE_DIRECTIVES: dict[str, str] = {

    "casual": """\
## Role this turn: Natural conversation

The user is greeting, making small talk, asking who you are, or what you can help with.
- Introduce yourself briefly as Luna — a companion for emotional wellness (not a doctor).
- If they ask what you can do: mention listening, gentle support, and simple techniques
  (breathing, grounding, CBT-style reflection) in plain everyday words — max 3 short points.
- Do NOT list clinical terms. Do NOT mention apps, ocean sounds, or exercises unless they ask.
- End with one warm question (e.g. how they are feeling today).
""",

    "reflective_listening": """\
## Role this turn: Reflective listening

The user is venting or sharing feelings and needs to feel heard, not advised.
1. Reflect back what they said in your own words (1–2 sentences).
2. Name the emotion you sense ("It sounds like you're feeling…").
3. Invite them to share more with one open, gentle question.
Do NOT offer advice, solutions, or analysis this turn.
""",

    "CBT": """\
## Role this turn: Cognitive Behavioural Therapy (CBT)

Apply gentle CBT in sequence:
1. Validate the emotion first (1 sentence — "That sounds really hard…").
2. Ask ONE Socratic question to explore the thought behind the feeling.
   E.g. "When that happened, what did you tell yourself?" or "What makes you believe that…?"
3. If a cognitive distortion is clearly present, name it very softly:
   "Sometimes our mind tends to see things as… [distortion type]."
Do NOT list distortions. Do NOT lecture. Keep the conversation natural.
""",

    "grounding": """\
## Role this turn: Grounding technique

The user is anxious, panicking, or needs to anchor to the present immediately.
- Guide them through the 5-4-3-2-1 technique OR box breathing (4-4-4-4) — choose whichever fits.
- Use short, rhythmic, present-tense instructions:
  "Look around and find 5 things you can see. Start now…"
- Keep a calm, gentle pace. Short sentences. Natural pauses.
- After the exercise, check in: "How are you feeling now?"
""",

    "behavioral_activation": """\
## Role this turn: Behavioural activation

The user has low mood, low motivation, or is withdrawing.
1. Briefly validate their mood without judgment.
2. Explain in one sentence why a small action can help.
3. Suggest ONE specific, easy activity doable within the next hour.
   E.g. "a 10-minute walk", "making a cup of tea by the window", "texting one friend".
Do not suggest multiple options. Do not lecture about the benefits of exercise.
""",

    "psychoeducation": """\
## Role this turn: Psychoeducation

The user is asking about a specific mental or physical health topic (not "what can you do").
- Share one clear, evidence-based insight in plain language — no jargon dumps.
- If "Curated knowledge snippets" are provided, weave them in naturally (do not quote verbatim).
- End with one gentle check-in in the user's language only
  (Vietnamese example: "Điều này có gần với những gì bạn đang trải qua không?").
""",

    "stabilization": """\
## Role this turn: Emotional stabilization

The user is experiencing significant distress.
Do NOT analyse, reframe, or give advice right now.
Only do three things:
1. Acknowledge their pain ("I hear you…").
2. Anchor them to the present: "Right now, you are safe."
3. Offer one small physical anchor: "Try placing both feet flat on the floor and notice the feeling."
Keep the reply very short (2–4 sentences). Tone: gentle and steady.
""",
}

# Fallback khi strategy không khớp
_DEFAULT_DIRECTIVE = ROLE_DIRECTIVES["reflective_listening"]

_META_PATTERNS = (
    "bạn là ai",
    "bạn là gì",
    "bạn có thể giúp",
    "giúp gì cho tôi",
    "làm được gì",
    "bạn làm được",
    "xin chào",
    "chào bạn",
    "chào luna",
    "hello",
    "hi luna",
    "who are you",
    "what can you",
    "what do you do",
)

# English template bleed-through from older prompts — strip when user writes Vietnamese
_ENGLISH_BLEED = (
    "does this relate to what you're going through?",
    "does this relate to what you are going through?",
)


def is_meta_conversation(text: str) -> bool:
    """Greetings, identity, or capability questions — not therapy content."""
    t = text.lower().strip()
    if not t:
        return False
    return any(p in t for p in _META_PATTERNS)


def detect_language(text: str, history: list[dict[str, str]] | None = None) -> str:
    """Return 'vi' or 'en' from recent user text."""
    blob = text
    if history:
        user_lines = [m.get("content", "") for m in history if m.get("role") == "user"][-3:]
        blob = " ".join(user_lines + [text])
    if re.search(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", blob, re.I):
        return "vi"
    vi_words = ("tôi", "bạn", "mình", "không", "cảm", "thấy", "chào", "giúp", "buồn", "lo")
    low = blob.lower()
    if sum(1 for w in vi_words if w in low) >= 2:
        return "vi"
    return "en"


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_system_prompt(
    strategy: str,
    intent: str,
    chunks: list[str],
    long_term: dict[str, Any],
    *,
    user_input: str = "",
    reply_language: str = "vi",
) -> str:
    """Assemble the 2-layer system prompt."""
    if intent == "casual" or is_meta_conversation(user_input):
        directive = ROLE_DIRECTIVES["casual"]
    else:
        directive = ROLE_DIRECTIVES.get(strategy, _DEFAULT_DIRECTIVE)

    # Curated knowledge snippets (RAG)
    if chunks:
        rag_block = "\n## Curated knowledge snippets\n" + "\n".join(f"- {c}" for c in chunks)
    else:
        rag_block = ""

    # Long-term user context
    lt_parts: list[str] = []
    if long_term.get("recurring_stressors"):
        lt_parts.append(f"- Recurring stressors: {', '.join(long_term['recurring_stressors'])}")
    if long_term.get("coping_preferences"):
        lt_parts.append(f"- Preferred coping methods: {', '.join(long_term['coping_preferences'])}")
    if long_term.get("mood_trend"):
        lt_parts.append(f"- Recent mood trend: {long_term['mood_trend']}")
    if long_term.get("preferred_tone"):
        lt_parts.append(f"- Preferred tone: {long_term['preferred_tone']}")
    lt_block = (
        "\n## User context (from previous sessions)\n" + "\n".join(lt_parts)
        if lt_parts else ""
    )

    lang_name = "Vietnamese" if reply_language == "vi" else "English"
    lang_block = (
        f"\n## Language for this reply\n"
        f"Write the entire reply in {lang_name} only. Do not use any other language.\n"
    )

    return f"{BASE_PERSONA}\n\n{directive}{lang_block}{rag_block}{lt_block}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _history_text(history: list[dict[str, str]], max_turns: int = 10) -> str:
    return "\n".join(
        f"{t.get('role', 'user')}: {t.get('content', '')}"
        for t in history[-max_turns:]
    )


def _sanitize(text: str, *, reply_language: str = "vi") -> str:
    cleaned: list[str] = []
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("coping idea:") or low.startswith("goal:"):
            continue
        if reply_language == "vi" and any(bleed in low for bleed in _ENGLISH_BLEED):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def node_response_generator(state: dict[str, Any]) -> dict[str, Any]:
    user_input: str = state.get("user_input", "")
    history: list[dict[str, str]] = state.get("history", [])
    provider: ProviderName = state.get("provider", "openai")
    strategy: str = state.get("therapy_strategy", "reflective_listening")
    intent: str = state.get("intent", "general_health")
    chunks: list[str] = state.get("retrieved_chunks") or []
    long_term: dict[str, Any] = state.get("long_term_context") or {}

    reply_language = detect_language(user_input, history)
    system_prompt = build_system_prompt(
        strategy,
        intent,
        chunks,
        long_term,
        user_input=user_input,
        reply_language=reply_language,
    )
    human_content = (
        f"Recent conversation:\n{_history_text(history)}\n\nLatest user message:\n{user_input}"
        if history
        else user_input
    )

    try:
        llm = get_chat_model(provider)
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=system_prompt), HumanMessage(content=human_content)],
            primary=provider,
        )
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        reply = _sanitize(text, reply_language=reply_language)
    except Exception as exc:
        logger.error("response_generator failed: %s", exc)
        reply = "Mình đang gặp chút vấn đề kỹ thuật. Bạn có thể thử lại không?"

    return {"final_reply": reply or "Mình ở đây với bạn. Bạn có thể chia sẻ thêm không?"}
