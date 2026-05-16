from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from app.config import ProviderName, get_settings

logger = logging.getLogger(__name__)
PREFERRED_PROVIDER_ORDER: tuple[ProviderName, ...] = ("modal", "openai", "gemini", "groq")


def _chat_openai_modal() -> BaseChatModel:
    s = get_settings()
    if not s.modal_base_url:
        raise ValueError("MODAL_BASE_URL is not set")
    return ChatOpenAI(
        base_url=s.modal_base_url.rstrip("/"),
        api_key=s.modal_api_key or "dummy",
        model=s.modal_model,
        temperature=0.4,
        timeout=60,
    )


def _chat_groq() -> BaseChatModel:
    s = get_settings()
    if not s.groq_api_key:
        raise ValueError("GROQ_API_KEY is not set")
    return ChatGroq(
        api_key=s.groq_api_key,
        model=s.groq_model,
        temperature=0.4,
        timeout=60,
    )


def _chat_openai() -> BaseChatModel:
    s = get_settings()
    if not s.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")
    return ChatOpenAI(
        api_key=s.openai_api_key,
        model=s.openai_model,
        temperature=0.4,
        timeout=60,
    )


def _chat_gemini() -> BaseChatModel:
    s = get_settings()
    if not s.google_api_key:
        raise ValueError("GOOGLE_API_KEY is not set")
    return ChatGoogleGenerativeAI(
        google_api_key=s.google_api_key,
        model=s.gemini_model,
        temperature=0.4,
    )


def get_chat_model(provider: ProviderName) -> BaseChatModel:
    if provider == "modal":
        return _chat_openai_modal()
    if provider == "groq":
        return _chat_groq()
    if provider == "openai":
        return _chat_openai()
    if provider == "gemini":
        return _chat_gemini()
    raise ValueError(f"Unknown provider: {provider}")


def parse_fallback_chain(chain: str) -> list[ProviderName]:
    order: list[ProviderName] = []
    for part in chain.split(","):
        p = part.strip().lower()
        if p in ("modal", "groq", "openai", "gemini"):
            order.append(p)  # type: ignore[arg-type]
    return order


def is_provider_configured(provider: ProviderName) -> bool:
    s = get_settings()
    if provider == "modal":
        return bool(s.modal_base_url)
    if provider == "openai":
        return bool(s.openai_api_key)
    if provider == "gemini":
        return bool(s.google_api_key)
    if provider == "groq":
        return bool(s.groq_api_key)
    return False


def build_provider_chain(primary: ProviderName) -> list[ProviderName]:
    """Return configured providers in code-defined priority, keeping `primary` first."""
    configured = [p for p in PREFERRED_PROVIDER_ORDER if is_provider_configured(p)]
    if primary in configured:
        return [primary] + [p for p in configured if p != primary]
    return [primary] + configured


async def invoke_with_fallback(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    *,
    primary: ProviderName,
) -> BaseMessage:
    chain = build_provider_chain(primary)
    last_err: Exception | None = None
    for prov in chain:
        try:
            model = get_chat_model(prov) if prov != primary else llm
            return await model.ainvoke(messages)
        except Exception as e:
            logger.warning("LLM provider %s failed: %s", prov, e)
            last_err = e
            await asyncio.sleep(0)
    if last_err:
        raise last_err
    raise RuntimeError("No LLM providers configured")


def resolve_provider(requested: str | None, default: ProviderName = "openai") -> ProviderName:
    if not requested:
        return default
    r = requested.strip().lower()
    if r in ("modal", "groq", "openai", "gemini"):
        return r  # type: ignore[return-value]
    return default


def default_provider() -> ProviderName:
    for p in PREFERRED_PROVIDER_ORDER:
        if is_provider_configured(p):
            return p
    return "openai"
