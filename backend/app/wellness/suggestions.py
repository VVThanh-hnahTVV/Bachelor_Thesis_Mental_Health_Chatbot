"""LLM-assisted selection of in-app wellness activities.

- **Tool agent** (``create_agent`` + ``get_activity``): native tool calls; when
  ``WELLNESS_AGENT_DEBUG=1``, traces are printed in **ReAct-style** lines
  (``Thought:`` / ``Action:`` / ``Action Input:`` / ``Observation:`` / ``Final Answer:``),
  analogous to LangChain ``ZERO_SHOT_REACT_DESCRIPTION`` + ``verbose=True`` (see e.g.
  ``learning_path.py`` in an AI Schedule–style project).
- **JSON planner**: plain chat + ``{"activity_ids": [...]}`` if tools fail or ``json_only``.

Env: ``WELLNESS_ACTIVITY_PLANNER`` = ``tool_first`` | ``tool_only`` | ``json_only``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Sequence

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.config import ProviderName
from app.llm.factory import build_provider_chain, get_chat_model, invoke_with_fallback
from app.loclog import loc_print

logger = logging.getLogger(__name__)


def _wellness_agent_debug() -> bool:
    return os.environ.get("WELLNESS_AGENT_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def _activity_planner_strategy() -> str:
    """``tool_first`` (default): agent + tools, then JSON if the agent run errors."""
    v = os.environ.get("WELLNESS_ACTIVITY_PLANNER", "tool_first").strip().lower()
    if v in ("json", "json_only"):
        return "json_only"
    if v in ("tool", "tools", "agent", "tool_only"):
        return "tool_only"
    return "tool_first"


def _short(text: object, max_len: int) -> str:
    s = str(text) if text is not None else ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _log_tool_agent_trace(messages: Sequence[Any]) -> None:
    """Print tool runs like classic ReAct verbose: Thought / Action / Action Input / Observation / Final Answer."""
    loc_print(
        "=== Wellness planner trace (ReAct-style labels; parallel to verbose ReAct agents) ==="
    )
    for i, msg in enumerate(messages):
        if isinstance(msg, SystemMessage):
            loc_print(f"[#{i}] (system) {_short(msg.content, 600)}")
        elif isinstance(msg, HumanMessage):
            loc_print(f"[#{i}] (user) {_short(msg.content, 800)}")
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                thought = (msg.content or "").strip()
                if thought:
                    loc_print(f"[#{i}] Thought: {_short(thought, 1200)}")
                else:
                    loc_print(f"[#{i}] Thought: (no text; model emitted tool call(s) only)")
                for tc in msg.tool_calls:
                    if isinstance(tc, dict):
                        name = tc.get("name") or ""
                        args = tc.get("args") or {}
                    else:
                        name = getattr(tc, "name", "") or ""
                        args = getattr(tc, "args", None) or {}
                    loc_print(f"[#{i}] Action: {name}")
                    try:
                        loc_print(
                            f"[#{i}] Action Input: {_short(json.dumps(args, ensure_ascii=False), 800)}"
                        )
                    except (TypeError, ValueError):
                        loc_print(f"[#{i}] Action Input: {_short(args, 800)}")
            elif msg.content:
                loc_print(f"[#{i}] Final Answer: {_short(msg.content, 1200)}")
        elif isinstance(msg, ToolMessage):
            loc_print(f"[#{i}] Observation: {_short(msg.content, 800)}")
        else:
            loc_print(f"[#{i}] {type(msg).__name__}: {_short(msg, 500)}")


ALLOWED_IDS = frozenset({"breathing_box", "ocean_sound"})

# Fixed copy for UI (ids come from LLM only from ALLOWED_IDS)
CATALOG: dict[str, tuple[str, str]] = {
    "breathing_box": (
        "Hít thở hộp (4-4-4-4)",
        "Nhịp thở đều trong app — hữu ích khi căng thẳng hoặc khi bạn muốn tập trung vào hơi thở.",
    ),
    "ocean_sound": (
        "Âm sóng nhẹ",
        "Âm nền dạng sóng trong app — phù hợp khi cần thư giãn, dễ ngủ hoặc giảm kích thích.",
    ),
}


def _tool_get_activity(activity_id: str) -> dict[str, str] | None:
    if activity_id not in ALLOWED_IDS:
        return None
    title, desc = CATALOG[activity_id]
    return {"id": activity_id, "title": title, "description": desc}


# Short bridge + cues: if metadata suggests an in-app activity but the model reply
# stayed generic, append a line so text matches what the UI button offers.
_REPLY_ALIGN: dict[str, tuple[str, tuple[str, ...]]] = {
    "ocean_sound": (
        "Nếu bạn muốn thử ngay: trong app có âm sóng nhẹ — bạn có thể mở và để nền âm đó đồng hành lúc thư giãn.",
        ("âm sóng", "sóng nhẹ", "âm nền", "mở âm", "trong app", "ambient", "ocean", "sóng biển"),
    ),
    "breathing_box": (
        "Trong app cũng có bài hít thở hộp (4-4-4-4) nếu bạn muốn thử một nhịp thở đều.",
        ("hít thở", "nhịp thở", "4-4-4", "thở hộp", "trong app", "hơi thở"),
    ),
}


def align_assistant_reply_with_suggestions(reply: str, suggestions: list[dict[str, str]]) -> str:
    """Keep assistant copy consistent with ``suggested_activities`` shown in the UI."""
    if not suggestions or not (reply or "").strip():
        return reply
    out = reply.strip()
    low = out.lower()
    used: set[str] = set()
    for item in suggestions:
        sid = str(item.get("id", "")).strip()
        if sid not in _REPLY_ALIGN or sid in used:
            continue
        used.add(sid)
        bridge, cues = _REPLY_ALIGN[sid]
        if any(c in low for c in cues):
            continue
        out = f"{out}\n\n{bridge}".strip()
        low = out.lower()
    return out


def _extract_message_text(msg: BaseMessage) -> str:
    c = getattr(msg, "content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(c)


def _parse_activity_id_list(text: str) -> list[str]:
    """Parse ``{"activity_ids": [...]}`` (or ``ids`` / ``activities``) from model output."""
    raw = text.strip()
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    arr = data.get("activity_ids")
    if arr is None:
        arr = data.get("ids")
    if arr is None:
        arr = data.get("activities")
    if not isinstance(arr, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for x in arr:
        aid = str(x).strip()
        if aid in ALLOWED_IDS and aid not in seen:
            seen.add(aid)
            out.append(aid)
        if len(out) >= 2:
            break
    return out


_SYSTEM_NORMAL = """You are a wellness planner. Reply with ONLY valid JSON (no markdown fences, no prose).
Schema: {"activity_ids": []}
Each string must be exactly "breathing_box" or "ocean_sound". At most 2 items.

Rules:
- breathing_box: only if breath/grounding genuinely helps and the user did NOT refuse breathing.
- ocean_sound: music, ambient waves, sleep wind-down, gentle relaxation without breath focus.
- For breakup, grief, anger, or pure venting with no in-app tool need, use [].
- If unsure, []."""


_SYSTEM_REFUSAL = """The user refused breathing exercises. Reply with ONLY valid JSON (no markdown fences, no prose).
Schema: {"activity_ids": []}
You may include ONLY "ocean_sound" (at most 2). Never "breathing_box".
Use ocean_sound only if calming audio / music / relaxation fits; otherwise []."""


async def _llm_plan_activity_ids(
    llm: Any,
    *,
    provider: ProviderName,
    system: str,
    user: str,
    strip_breathing: bool,
) -> list[str]:
    messages: list[BaseMessage] = [SystemMessage(content=system), HumanMessage(content=user)]
    try:
        resp = await invoke_with_fallback(llm, messages, primary=provider)
    except Exception as e:
        logger.warning("activity planner LLM failed: %s", e)
        return []
    text = _extract_message_text(resp)
    if _wellness_agent_debug():
        loc_print(f"[wellness-planner] raw model reply: {_short(text, 2000)}")
    ids = _parse_activity_id_list(text)
    if strip_breathing:
        ids = [x for x in ids if x != "breathing_box"][:2]
    return ids[:2]


_AGENT_SYSTEM_NORMAL = """You are a wellness planner agent.
Call get_activity(activity_id) only when an in-app tool genuinely helps.
Allowed ids: breathing_box, ocean_sound.
Use breathing_box only if the user is open to it and needs grounding (stress spike, panic cue, or they ask).
Never push breathing after the user refused it (check recent messages).
Use ocean_sound for music, ambient sound, sleep wind-down, or gentle relaxation without breathing focus.
For breakup, grief, anger — prefer listening/support; do NOT default to breathing unless user asks.
If unsure, call no tools."""


_AGENT_SYSTEM_REFUSAL = """The user has refused breathing exercises. NEVER call get_activity(breathing_box).
You may call get_activity(ocean_sound) only if calming audio / music / relaxation fits.
Otherwise call no tools."""


async def _tool_agent_plan_activity_ids(
    *,
    provider: ProviderName,
    user_prompt: str,
    refusal: bool,
) -> list[str]:
    """Run ``create_agent`` + ``get_activity``; try providers in fallback order on hard errors."""
    chain: list[ProviderName] = build_provider_chain(provider)
    system = _AGENT_SYSTEM_REFUSAL if refusal else _AGENT_SYSTEM_NORMAL
    for prov in chain:
        selected_ids: list[str] = []
        try:
            llm = get_chat_model(prov)
        except Exception as e:
            logger.warning("activity planner: skip provider %s (init): %s", prov, e)
            continue

        @tool
        def get_activity(activity_id: str) -> str:
            """Select a wellness activity id. Use only: breathing_box or ocean_sound."""
            aid = str(activity_id).strip()
            if refusal and aid == "breathing_box":
                return "ignored_user_refused_breathing"
            if aid in ALLOWED_IDS and aid not in selected_ids:
                selected_ids.append(aid)
                return f"selected:{aid}"
            return "ignored"

        try:
            agent = create_agent(
                model=llm,
                tools=[get_activity],
                system_prompt=system,
                debug=_wellness_agent_debug(),
            )
            state = await agent.ainvoke({"messages": [{"role": "user", "content": user_prompt}]})
            if _wellness_agent_debug():
                _log_tool_agent_trace(state.get("messages", []))
        except Exception as e:
            logger.warning("activity planner tool agent failed (provider=%s): %s", prov, e)
            continue
        out = [x for x in selected_ids if not (refusal and x == "breathing_box")][:2]
        return out
    return []


def _user_refuses_breathing(text: str) -> bool:
    t = text.lower()
    refusal_markers = (
        "không hít",
        "đéo hít",
        "deo hit",
        "không muốn thở",
        "không cần thở",
        "đừng bảo tôi thở",
        "đừng bảo thở",
        "bỏ thở",
        "không thở",
        "no breathing",
        "stop telling me to breathe",
    )
    return any(m in t for m in refusal_markers)


def _fallback_activity_ids(user_input: str, assistant_reply: str) -> list[str]:
    combined = f"{user_input}\n{assistant_reply}"
    text = combined.lower()
    ids: list[str] = []
    refused_breath = _user_refuses_breathing(combined)
    # Tight triggers only (avoid substring "tho" / bare "thở" — too many false positives).
    breath_hints = (
        "hít thở",
        "hít sâu",
        "thở sâu",
        "thở đều",
        "hit tho",
        "breath",
        "breathing",
        "4 giây",
        "4-4-4",
        "nhịp thở",
    )
    if not refused_breath and any(k in text for k in breath_hints):
        ids.append("breathing_box")
    calm_hints = (
        "nhạc",
        "nghe nhạc",
        "music",
        "âm sóng",
        "ocean",
        "sóng biển",
        "wave",
        "ambient",
        "thư giãn",
        "relax",
        "bài tập khác",
        "làm cái khác",
        "gợi ý khác",
    )
    if any(k in text for k in calm_hints):
        ids.append("ocean_sound")
    # Keep order stable and max 2
    seen: set[str] = set()
    out: list[str] = []
    for aid in ids:
        if aid not in seen:
            seen.add(aid)
            out.append(aid)
    return out[:2]


async def detect_suggested_activities_llm(
    *,
    user_input: str,
    assistant_reply: str,
    risk_level: str,
    provider: ProviderName,
    recent_user_messages: str | None = None,
) -> list[dict[str, str]]:
    if risk_level == "high":
        return []
    recent = (recent_user_messages or user_input).strip()
    if _user_refuses_breathing(recent) or _user_refuses_breathing(user_input):
        # User opted out of breathing — still allow ocean_sound via tool agent / JSON / heuristics.
        prompt = (
            f"risk_level: {risk_level}\n"
            f"Recent user messages:\n{recent}\n\n"
            f"Latest user message: {user_input}\n"
            f"Latest assistant reply: {assistant_reply}\n"
        )
        strat = _activity_planner_strategy()
        out_ids: list[str] = []
        if strat in ("tool_first", "tool_only"):
            out_ids = await _tool_agent_plan_activity_ids(
                provider=provider, user_prompt=prompt, refusal=True
            )
        if not out_ids and strat in ("tool_first", "json_only"):
            llm = get_chat_model(provider)
            out_ids = await _llm_plan_activity_ids(
                llm,
                provider=provider,
                system=_SYSTEM_REFUSAL,
                user=prompt,
                strip_breathing=True,
            )
        if not out_ids:
            # Fallback: no breathing; ocean if cues present
            t = f"{user_input}\n{assistant_reply}".lower()
            if any(
                k in t
                for k in (
                    "nhạc",
                    "music",
                    "âm sóng",
                    "ocean",
                    "sóng",
                    "wave",
                    "thư giãn",
                    "relax",
                    "bài tập khác",
                    "làm cái khác",
                )
            ):
                out_ids = ["ocean_sound"]
        result: list[dict[str, str]] = []
        for aid in out_ids:
            item = _tool_get_activity(aid)
            if item:
                result.append(item)
        return result

    prompt = (
        f"risk_level: {risk_level}\n"
        f"Recent user messages:\n{recent}\n\n"
        f"Latest user message: {user_input}\n"
        f"Latest assistant reply: {assistant_reply}\n"
    )
    strat = _activity_planner_strategy()
    ids: list[str] = []
    if strat in ("tool_first", "tool_only"):
        ids = await _tool_agent_plan_activity_ids(
            provider=provider, user_prompt=prompt, refusal=False
        )
    if not ids and strat in ("tool_first", "json_only"):
        llm = get_chat_model(provider)
        ids = await _llm_plan_activity_ids(
            llm,
            provider=provider,
            system=_SYSTEM_NORMAL,
            user=prompt,
            strip_breathing=False,
        )

    if not ids:
        ids = _fallback_activity_ids(user_input, assistant_reply)

    out: list[dict[str, str]] = []
    for aid in ids:
        item = _tool_get_activity(aid)
        if item:
            out.append(item)
    return out
