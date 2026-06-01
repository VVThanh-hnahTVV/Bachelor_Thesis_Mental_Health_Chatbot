"""Chat LLM builders for medical agents (Groq via thesis settings)."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from langchain_groq import ChatGroq

from app.config import get_settings


def build_chat_llm(temperature: float, *, for_vision: bool = False) -> BaseChatModel:
    """Medical agents use Groq; vision uses same model when scout supports images."""
    _ = for_vision
    s = get_settings()
    if not s.groq_api_key:
        raise ValueError("GROQ_API_KEY is required for medical mode")
    return ChatGroq(
        api_key=s.groq_api_key,
        model=s.groq_model,
        temperature=temperature,
        timeout=120,
    )
