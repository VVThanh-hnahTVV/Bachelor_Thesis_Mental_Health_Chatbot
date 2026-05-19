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
from app.graph.script_bank import resolve_script_reply
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
- Sound like a caring friend: warm, sincere, respectful, never curt or robotic.
- Greetings deserve genuine warmth (2–4 sentences): greet back, show you are glad they
  reached out, briefly that you are here to listen and support — then one gentle question.
- Other turns: concise but caring (roughly 2–5 sentences unless guiding breathing).
- Ask at most one gentle follow-up question when it fits.
- Vary wording naturally across turns. Do not reuse the same opening sentence repeatedly.

**Healing focus (Wysa-style — hear AND gently heal):**
- Your purpose is to help the user feel heard and gradually feel a little better — stay with THEIR
  story (loss, conflict, fear, anger, loneliness, etc.), not generic check-ins.
- Read the full conversation. Reference specific details they already shared.
- Each reply should move gently forward: validate → normalize ("it's okay to feel…") → optional
  gentle positive reframe (pain can show how much something mattered) → one caring next step.
- Do NOT spiral deeper into pain with repeated "what sensations / thoughts / images arise?" questions.
  After the user has named feelings, memories, and body sensations, offer comfort or a small coping
  step instead of another probe.
- Encourage and uplift where honest: name their strength, the meaning of what they care about,
  or that their feelings make sense — without toxic positivity or dismissing pain.

**Never:**
- Mix Vietnamese and English in the same reply.
- Copy template phrases from instructions (e.g. "Does this relate to what you're going through?").
- Use empty generic lines such as "It seems you're dealing with something tough",
  "Would you like to share a bit more?", or "going through something hard" without naming
  what they told you.
- Ask more than one follow-up question, or chain multiple exploratory questions in one reply.
- Repeat probing patterns: "what sensations arise", "what thoughts come forward",
  "what images stand out", "when those pictures surface".
- Fabricate medical facts or make diagnoses.
- Say "I'm just an AI" or refuse normal conversation.
- Over-analyse when the user simply wants to be heard.
- Push breathing exercises, apps, or tools unless the user is anxious, shows body distress,
  has vented several turns, or asks for help.
- Suggest professional help in a robotic way — only when truly necessary, and naturally.
"""

# ---------------------------------------------------------------------------
# Layer 2 — ROLE DIRECTIVES
# Tells Luna WHAT to do this specific turn.
# Each strategy is a focused, actionable instruction set.
# ---------------------------------------------------------------------------

ROLE_DIRECTIVES: dict[str, str] = {

    "casual": """\
## Role this turn: Warm greeting or small talk

The user is greeting you or opening the conversation.
- Respond with sincere warmth and respect — never a bare "Chào bạn" or one-liner.
- Structure (Vietnamese example tone):
  1) Greet them back kindly.
  2) Briefly introduce yourself as Luna, a companion for emotional wellness.
  3) Show genuine willingness to listen and support, without pressure.
  4) End with one caring question about how they feel today.
- Do NOT list services like a menu. Do NOT mention apps or breathing unless they ask.
- Do NOT say "Bạn muốn làm gì hôm nay".
""",

    "reflective_listening": """\
## Role this turn: Reflective listening with gentle healing

The user is venting or sharing feelings. Hear them AND help them feel a little held — not interrogated.
1. Reflect back SPECIFIC content they mentioned (names, events, memories, body sensations they named).
2. Validate and normalize briefly (e.g. "It's okay to feel that sadness" / "Cảm buồn như vậy là điều tự nhiên").
3. When they share painful memories or what they miss, add ONE short positive
   reframe if it fits: the pain can show how much it mattered — one sentence only.
4. End with ONE of these (pick the better fit — not both):
   - Early sharing (they have not yet named body sensations or what hurts most): one caring question
     about what feels hardest or what they miss most — tied to their words.
   - They already named feelings, memories, AND body sensations (or 3+ turns of grief): do NOT ask
     what sensations/thoughts/images "arise" again. Offer a gentle next step instead, e.g.
     "Would you like to try a short grounding exercise together?" or ask if they want comfort
     rather than more detail about the pain.
5. Optional: one warm metaphor linking body and heart (e.g. body holding what the heart feels).

Do NOT offer advice lists, CBT lecturing, or multiple questions.
Do NOT use vague prompts like "something tough" or "a bit more" without context.
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
## Role this turn: Gentle grounding (healing step)

The user is anxious, physically tense (chest tightness, lump in throat), panicking, or ready for calm.
- If they have NOT clearly agreed yet (no yes/ok/sure/được/muốn thử in their latest message):
  1) Acknowledge their state with empathy (name what they shared).
  2) Optional gentle metaphor (body holding what the heart feels).
  3) Ask permission only: "Would you like to try a gentle grounding exercise together?"
  Do NOT give full steps yet — wait for agreement.
- If they agreed OR this is a follow-up to your offer:
  Guide ONE simple exercise in short present-tense steps (Wysa-style):
  comfortable seat → feet on the floor → slow breath in through nose, hold briefly, out through mouth.
  2–4 short sentences. Then one check-in: "How does that feel so far?"
- For acute panic, you may use 5-4-3-2-1 instead of breathing.
- Do NOT ask what thoughts, memories, or sensations arise. Do NOT probe grief deeper.
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

    "objection": """\
## Role this turn: Recover from misunderstanding

The user felt misunderstood, refused a suggestion, or asked you to stop repeating.
1. Apologize briefly and sincerely (one sentence).
2. Reflect what you think they meant — ask if you got it right.
3. Do NOT suggest breathing, apps, tools, or new techniques.
4. Do NOT repeat your previous advice.
Keep it to 2–4 short sentences. Warm, humble tone.
""",

    "stabilization": """\
## Role this turn: Emotional stabilization

The user is experiencing significant distress.
Do NOT analyse, reframe, or give advice right now.
Only do three things:
1. Acknowledge their pain ("I hear you…").
2. Anchor them to the present: "Right now, you are safe."
3. Offer one small physical anchor: "Try placing both feet flat on the floor and notice the feeling."
Suggest the feet-on-floor anchor at most ONCE per conversation — if it was already offered, skip it and only validate + check in.
Keep the reply very short (2–4 sentences). Tone: gentle and steady.
""",

    "post_stabilization": """\
## Role this turn: After a brief calming exercise

The user has tried or finished a short grounding step. Do NOT repeat feet-on-floor or breathing instructions.
1. Acknowledge their effort (one sentence).
2. Ask ONE specific, caring question about what matters most right now
   (e.g. the relationship, what hurts most, or one small next step they want).
3. Do NOT use generic "share more" or "do you want to talk more" phrasing.
Keep it warm and concise (2–4 sentences).
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
    latest = text or ""
    if re.search(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", latest, re.I):
        return "vi"
    # Prioritize current message language first; only fallback to history when
    # the latest message is too short or ambiguous (e.g. "ok", "hmm").
    if re.search(r"\b(i|me|my|you|know|help|feel|do)\b", latest.lower()):
        return "en"
    blob = latest
    if history:
        user_lines = [m.get("content", "") for m in history if m.get("role") == "user"][-3:]
        blob = " ".join(user_lines + [latest])
    vi_words = ("tôi", "bạn", "mình", "không", "cảm", "thấy", "chào", "giúp", "buồn", "lo")
    low = blob.lower()
    if sum(1 for w in vi_words if w in low) >= 2:
        return "vi"
    return "en"


def _is_known_user_query(text: str) -> bool:
    t = text.lower().strip()
    patterns = (
        "do you know me",
        "you know me",
        "bạn biết mình là ai",
        "bạn biết tôi là ai",
        "biết mình là ai không",
        "biết tôi là ai không",
    )
    return any(p in t for p in patterns)


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
    objection_detected: bool = False,
    therapy_flags: dict[str, Any] | None = None,
) -> str:
    """Assemble the 2-layer system prompt."""
    flags = therapy_flags or {}
    if objection_detected:
        directive = ROLE_DIRECTIVES["objection"]
    elif intent == "casual" or is_meta_conversation(user_input):
        directive = ROLE_DIRECTIVES["casual"]
    elif strategy == "post_stabilization" or (
        flags.get("stabilization_turn")
        and strategy in ("reflective_listening", "CBT")
        and flags.get("last_strategy") == "stabilization"
    ):
        directive = ROLE_DIRECTIVES["post_stabilization"]
    else:
        directive = ROLE_DIRECTIVES.get(strategy, _DEFAULT_DIRECTIVE)

    # Curated knowledge snippets (RAG)
    if chunks:
        rag_block = (
            "\n## Curated knowledge snippets\n"
            "Use these only if they directly help answer the latest message. "
            "If they are weakly related, ignore them.\n"
            + "\n".join(f"- {c}" for c in chunks)
        )
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
    if long_term.get("recent_mood_notes"):
        lt_parts.append(
            f"- Recent mood highlights: {' | '.join(long_term['recent_mood_notes'])}"
        )
    if long_term.get("preferred_tone"):
        lt_parts.append(f"- Preferred tone: {long_term['preferred_tone']}")
    if long_term.get("user_display_name"):
        lt_parts.append(f"- User display name: {long_term['user_display_name']}")
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
    objection_detected: bool = bool(state.get("objection_detected"))
    chunks: list[str] = state.get("retrieved_chunks") or []
    long_term: dict[str, Any] = state.get("long_term_context") or {}
    therapy_flags: dict[str, Any] = state.get("therapy_flags") or {}

    reply_language = detect_language(user_input, history)
    if _is_known_user_query(user_input):
        display_name = str(long_term.get("user_display_name") or "").strip()
        if display_name:
            if reply_language == "vi":
                return {
                    "final_reply": (
                        f"Mình nhớ bạn là {display_name}. "
                        "Mình sẽ đồng hành cùng bạn theo đúng bối cảnh và cảm xúc bạn đã chia sẻ trước đó."
                    )
                }
            return {
                "final_reply": (
                    f"Yes, I remember you as {display_name}. "
                    "I'll personalize my support based on your previous context and mood."
                )
            }

    scripted = await resolve_script_reply(
        user_input=user_input,
        intent=intent,
        strategy=strategy,
        objection_detected=objection_detected,
        lang=reply_language,
        provider=provider,
        history=history,
    )
    if scripted:
        return {"final_reply": _sanitize(scripted, reply_language=reply_language)}

    system_prompt = build_system_prompt(
        strategy,
        intent,
        chunks,
        long_term,
        user_input=user_input,
        reply_language=reply_language,
        objection_detected=objection_detected,
        therapy_flags=therapy_flags,
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
