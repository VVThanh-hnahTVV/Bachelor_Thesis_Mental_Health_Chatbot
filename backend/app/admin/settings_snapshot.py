"""Read-only admin snapshot of effective AI / system configuration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import get_settings
from app.llm.factory import build_provider_chain, default_provider, is_provider_configured
from app.medical.config import get_medical_config
from app.medical.llm import resolve_ingest_provider
from app.rag.embeddings import resolve_embedding_model, resolve_embedding_provider


def _mask_secret(value: str | None) -> dict[str, Any]:
    if not value or not value.strip():
        return {"configured": False, "masked": None}
    trimmed = value.strip()
    if len(trimmed) <= 4:
        return {"configured": True, "masked": "****"}
    return {"configured": True, "masked": f"…{trimmed[-4:]}"}


def _provider_row(name: str, *, model: str, base_url: str | None = None) -> dict[str, Any]:
    configured = is_provider_configured(name)  # type: ignore[arg-type]
    s = get_settings()
    key_map = {
        "local": None,
        "modal": s.modal_api_key,
        "groq": s.groq_api_key,
        "openai": s.openai_api_key,
        "gemini": s.google_api_key,
    }
    row: dict[str, Any] = {
        "name": name,
        "configured": configured,
        "model": model,
        "api_key": _mask_secret(key_map.get(name)),
    }
    if base_url:
        row["base_url"] = base_url
    return row


def build_admin_settings_snapshot() -> dict[str, Any]:
    s = get_settings()
    med = get_medical_config()
    primary = default_provider()
    chain = build_provider_chain(primary)
    active_model = {
        "local": s.local_model,
        "modal": s.modal_model,
        "groq": s.groq_model,
        "openai": s.openai_model,
        "gemini": s.gemini_model,
    }.get(primary, s.openai_model)
    emb_provider = resolve_embedding_provider()
    emb_model = resolve_embedding_model(emb_provider)

    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "read_only_note": "Cấu hình đọc từ .env lúc khởi động. Thay đổi cần restart backend.",
        "llm": {
            "primary_provider": primary,
            "active_model": active_model,
            "fallback_chain": list(chain),
            "fallback_chain_env": s.llm_fallback_chain,
            "enable_local_chat": s.enable_local_chat,
            "debug_llm_prompts": s.debug_llm_prompts,
            "ingest_llm_provider": resolve_ingest_provider(),
            "providers": [
                _provider_row(
                    "groq",
                    model=s.groq_model,
                ),
                _provider_row(
                    "openai",
                    model=s.openai_model,
                ),
                _provider_row(
                    "gemini",
                    model=s.gemini_model,
                ),
                _provider_row(
                    "local",
                    model=s.local_model,
                    base_url=s.local_base_url,
                ),
                _provider_row(
                    "modal",
                    model=s.modal_model,
                    base_url=s.modal_base_url,
                ),
            ],
        },
        "rag": {
            "embedding_provider": emb_provider,
            "embedding_model": emb_model,
            "chunk_size_words": med.rag.chunk_size,
            "chunk_overlap_words": med.rag.chunk_overlap,
            "chunk_batch_max_words": med.rag.chunk_batch_max_words,
            "enable_llm_chunking": med.rag.enable_llm_chunking,
            "top_k": med.rag.top_k,
            "reranker_top_k": med.rag.reranker_top_k,
            "min_retrieval_confidence": med.rag.min_retrieval_confidence,
            "vector_search_type": med.rag.vector_search_type,
            "distance_metric": med.rag.distance_metric,
            "collections": {
                "pdf_rag": med.rag.collection_name,
                "web_corpus": med.web_corpus.collection_name,
                "wellness": med.wellness.collection_name,
            },
            "qdrant_url": med.rag.url or "(local)",
            "vector_local_path": med.rag.vector_local_path,
            "wellness_top_k": med.wellness.top_k,
            "wellness_min_score": med.wellness.min_score,
            "wellness_suggestion_min_score": med.wellness.suggestion_min_score,
        },
        "web_search": {
            "enable_tavily": med.web_search.enable_tavily,
            "enable_pubmed": med.web_search.enable_pubmed,
            "tavily_max_results": med.web_search.tavily_max_results,
            "tavily_search_depth": med.web_search.tavily_search_depth,
            "tavily_include_domains": med.web_search.tavily_include_domains,
            "tavily_api_key": _mask_secret(med.web_search.tavily_api_key),
            "pubmed_max_results": med.web_search.pubmed_max_results,
            "pubmed_use_ncbi": med.web_search.pubmed_use_ncbi,
            "pubmed_europepmc_fallback": med.web_search.pubmed_europepmc_fallback,
            "pubmed_email": med.web_search.pubmed_email,
            "pubmed_api_key": _mask_secret(med.web_search.pubmed_api_key),
            "context_limit": med.web_search.context_limit,
        },
        "guardrails": {
            "enable_input_guardrails": s.enable_input_guardrails,
            "enable_output_guardrails": s.enable_output_guardrails,
            "input_checks": [
                "Harmful / illegal content",
                "PII detection",
                "Self-harm (block instructions)",
                "Prompt injection",
                "Off-topic non-medical requests",
            ],
            "output_checks": [
                "Safety & ethics review",
                "Localization to user language",
                "System prompt leak prevention",
            ],
            "model_source": "Shared medical chat LLM (RAG config)",
        },
        "system": {
            "enable_medical_mode": s.enable_medical_mode,
            "mongo_db_name": s.mongo_db_name,
            "redis_url": s.redis_url.split("@")[-1] if "@" in s.redis_url else s.redis_url,
            "cors_origins": s.cors_origins_list,
            "conversation_summary_max_tokens": s.conversation_summary_max_tokens,
        },
    }
