"""Chat LLM builders for medical agents."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from app.config import ProviderName, get_settings
from app.llm.factory import default_provider


def build_chat_llm(temperature: float, *, for_vision: bool = False) -> BaseChatModel:
    """Medical mode uses the same provider-priority selection as psychologist mode."""
    _ = for_vision
    s = get_settings()
    provider: ProviderName = default_provider()

    if provider == "local":
        if not s.local_base_url:
            raise ValueError("LOCAL_BASE_URL is not set")
        return ChatOpenAI(
            base_url=s.local_base_url.rstrip("/"),
            api_key=s.local_api_key or "ollama",
            model=s.local_model,
            temperature=temperature,
            timeout=120,
        )

    if provider == "modal":
        if not s.modal_base_url:
            raise ValueError("MODAL_BASE_URL is not set")
        return ChatOpenAI(
            base_url=s.modal_base_url.rstrip("/"),
            api_key=s.modal_api_key or "dummy",
            model=s.modal_model,
            temperature=temperature,
            timeout=120,
        )

    if provider == "openai":
        if not s.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        return ChatOpenAI(
            api_key=s.openai_api_key,
            model=s.openai_model,
            temperature=temperature,
            timeout=120,
        )

    if provider == "gemini":
        if not s.google_api_key:
            raise ValueError("GOOGLE_API_KEY is not set")
        return ChatGoogleGenerativeAI(
            google_api_key=s.google_api_key,
            model=s.gemini_model,
            temperature=temperature,
        )

    if not s.groq_api_key:
        raise ValueError("GROQ_API_KEY is not set")
    return ChatGroq(
        api_key=s.groq_api_key,
        model=s.groq_model,
        temperature=temperature,
        timeout=120,
    )
