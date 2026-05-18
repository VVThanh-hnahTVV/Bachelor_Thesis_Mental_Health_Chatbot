"""Clinician-reviewed script bank — match scenarios and optional LLM paraphrase."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName
from app.llm.factory import get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

_BANK_PATH = Path(__file__).resolve().parent.parent / "content" / "script_bank.json"

_PARAPHRASE_SYSTEM = """\
You paraphrase a fixed mental-health script. Rules:
- Keep the SAME meaning. Never shorten — same or slightly warmer tone, equal length.
- Do NOT strip greetings down to one short phrase.
- Do NOT add advice, tools, diagnoses, or new topics.
- Match the user's language exactly.
- Output only the paraphrased message, no quotes or labels.
"""


@dataclass
class Scenario:
    id: str
    keywords: list[str]
    intents: list[str]
    strategies: list[str]
    objection_only: bool
    templates: dict[str, str]
    allow_llm_paraphrase: bool
    max_sentences: int
    priority: int


_scenarios: list[Scenario] | None = None


def _load_scenarios() -> list[Scenario]:
    global _scenarios
    if _scenarios is not None:
        return _scenarios
    raw = json.loads(_BANK_PATH.read_text(encoding="utf-8"))
    out: list[Scenario] = []
    for item in raw.get("scenarios", []):
        out.append(
            Scenario(
                id=str(item["id"]),
                keywords=[str(k).lower() for k in item.get("keywords", [])],
                intents=[str(i).lower() for i in item.get("intents", [])],
                strategies=[str(s) for s in item.get("strategies", [])],
                objection_only=bool(item.get("objection_only", False)),
                templates=dict(item.get("templates", {})),
                allow_llm_paraphrase=bool(item.get("allow_llm_paraphrase", True)),
                max_sentences=int(item.get("max_sentences", 4)),
                priority=int(item.get("priority", 0)),
            )
        )
    _scenarios = sorted(out, key=lambda s: -s.priority)
    return _scenarios


def reload_scenarios() -> None:
    global _scenarios
    _scenarios = None
    _load_scenarios()


def match_scenario(
    user_input: str,
    *,
    intent: str = "",
    strategy: str = "",
    objection_detected: bool = False,
) -> Scenario | None:
    text = user_input.lower().strip()
    if not text:
        return None
    for sc in _load_scenarios():
        if sc.objection_only:
            if not objection_detected:
                continue
        elif objection_detected and sc.id not in ("refuse_breathing",):
            # prefer objection_apology via objection_only scenarios first
            pass
        if sc.intents and intent not in sc.intents:
            continue
        if sc.strategies and strategy and strategy not in sc.strategies:
            continue
        if sc.keywords and not any(k in text for k in sc.keywords):
            continue
        return sc
    return None


def render_template(scenario: Scenario, lang: str) -> str:
    tpl = scenario.templates.get(lang) or scenario.templates.get("vi") or ""
    return tpl.strip()


async def resolve_script_reply(
    *,
    user_input: str,
    intent: str,
    strategy: str,
    objection_detected: bool,
    lang: str,
    provider: ProviderName,
    history: list[dict[str, str]],
) -> str | None:
    """Return scripted reply if a scenario matches, else None."""
    sc = match_scenario(
        user_input,
        intent=intent,
        strategy=strategy,
        objection_detected=objection_detected,
    )
    if sc is None:
        return None
    base = render_template(sc, lang)
    if not base:
        return None
    if not sc.allow_llm_paraphrase:
        return base
    try:
        llm = get_chat_model(provider)
        human = f"Script to paraphrase:\n{base}\n\nUser message:\n{user_input}"
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=_PARAPHRASE_SYSTEM), HumanMessage(content=human)],
            primary=provider,
        )
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        text = text.strip()
        if text:
            sentences = re.split(r"(?<=[.!?…])\s+", text)
            if len(sentences) > sc.max_sentences:
                text = " ".join(sentences[: sc.max_sentences])
            # Reject over-short paraphrase (e.g. "Chào bạn" only)
            if len(text) >= max(40, int(len(base) * 0.65)):
                return text
    except Exception as exc:
        logger.warning("script paraphrase failed for %s: %s", sc.id, exc)
    return base
