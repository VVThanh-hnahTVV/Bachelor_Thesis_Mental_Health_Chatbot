"""Chat LLM builders for medical agents."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from app.config import ProviderName, get_settings
from app.llm.factory import default_provider, is_provider_configured


def _log_medical_input(input: Any) -> None:
    if not get_settings().debug_llm_prompts:
        return
    from app.loclog import coerce_llm_input_to_messages, infer_caller_label, print_llm_prompt

    label = infer_caller_label(prefix="medical")
    messages = coerce_llm_input_to_messages(input)
    print_llm_prompt(label, default_provider(), messages)


def _log_medical_usage(llm: Any, result: Any) -> None:
    if not get_settings().debug_llm_prompts:
        return
    usage = getattr(result, "usage_metadata", None)
    if not usage:
        return
    from app.loclog import infer_caller_label, loc_print

    label = infer_caller_label(prefix="medical")
    model = getattr(llm, "model_name", None) or getattr(llm, "model", "")
    loc_print(
        f"LLM TOKENS  label={label}  model={model}  "
        f"input={usage.get('input_tokens')}  output={usage.get('output_tokens')}  "
        f"total={usage.get('total_tokens')}"
    )


class _LoggingMixin:
    def invoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        _log_medical_input(input)
        result = super().invoke(input, config, **kwargs)
        _log_medical_usage(self, result)
        return result

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        _log_medical_input(input)
        result = await super().ainvoke(input, config, **kwargs)
        _log_medical_usage(self, result)
        return result


class LoggingChatOpenAI(_LoggingMixin, ChatOpenAI):
    pass


class LoggingChatGroq(_LoggingMixin, ChatGroq):
    pass


class LoggingChatGemini(_LoggingMixin, ChatGoogleGenerativeAI):
    pass


def resolve_ingest_provider() -> ProviderName:
    """Provider for PDF ingest (image summary + chunking). Defaults to OpenAI when configured."""
    explicit = os.getenv("INGEST_LLM_PROVIDER", "").strip().lower()
    if explicit in ("local", "modal", "groq", "openai", "gemini"):
        return explicit  # type: ignore[return-value]
    if is_provider_configured("openai"):
        return "openai"
    return default_provider()


def build_chat_llm(
    temperature: float,
    *,
    for_vision: bool = False,
    provider: ProviderName | None = None,
    model: str | None = None,
    timeout: int = 120,
) -> BaseChatModel:
    """Medical mode uses the shared multi-provider LLM factory."""
    _ = for_vision
    s = get_settings()
    selected: ProviderName = provider or default_provider()

    if selected == "local":
        if not s.local_base_url:
            raise ValueError("LOCAL_BASE_URL is not set")
        return LoggingChatOpenAI(
            base_url=s.local_base_url.rstrip("/"),
            api_key=s.local_api_key or "ollama",
            model=model or s.local_model,
            temperature=temperature,
            timeout=timeout,
        )

    if selected == "modal":
        if not s.modal_base_url:
            raise ValueError("MODAL_BASE_URL is not set")
        return LoggingChatOpenAI(
            base_url=s.modal_base_url.rstrip("/"),
            api_key=s.modal_api_key or "dummy",
            model=model or s.modal_model,
            temperature=temperature,
            timeout=timeout,
        )

    if selected == "openai":
        if not s.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        return LoggingChatOpenAI(
            api_key=s.openai_api_key,
            model=model or s.openai_model,
            temperature=temperature,
            timeout=timeout,
        )

    if selected == "gemini":
        if not s.google_api_key:
            raise ValueError("GOOGLE_API_KEY is not set")
        return LoggingChatGemini(
            google_api_key=s.google_api_key,
            model=model or s.gemini_model,
            temperature=temperature,
        )

    if not s.groq_api_key:
        raise ValueError("GROQ_API_KEY is not set")
    return LoggingChatGroq(
        api_key=s.groq_api_key,
        model=model or s.groq_model,
        temperature=temperature,
        timeout=timeout,
    )


def build_ingest_llm(temperature: float, *, for_vision: bool = False) -> BaseChatModel:
    """LLM for medical PDF ingest (summarize images, semantic chunking)."""
    provider = resolve_ingest_provider()
    ingest_model = os.getenv("INGEST_OPENAI_MODEL") or os.getenv("OPENAI_MODEL")
    timeout = 300 if for_vision else 180
    return build_chat_llm(
        temperature,
        for_vision=for_vision,
        provider=provider,
        model=ingest_model if provider == "openai" else None,
        timeout=timeout,
    )
