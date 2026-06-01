"""LangChain-compatible embeddings for medical Qdrant RAG."""

from __future__ import annotations

import asyncio
import os
from typing import List

from langchain_core.embeddings import Embeddings

from app.config import get_settings
from app.rag.embeddings import embed_documents, embed_text


def get_embedding_provider() -> str:
    return (os.getenv("EMBEDDING_PROVIDER") or get_settings().embedding_provider).lower()


def get_embedding_dim(provider: str | None = None) -> int:
    provider = provider or get_embedding_provider()
    if provider == "ollama":
        return int(os.getenv("OLLAMA_EMBEDDING_DIM", "768"))
    return int(os.getenv("AZURE_EMBEDDING_DIM", "1536"))


def get_qdrant_collection_name(
    provider: str | None = None, embedding_dim: int | None = None
) -> str:
    if os.getenv("QDRANT_COLLECTION_NAME"):
        return os.getenv("QDRANT_COLLECTION_NAME", "")
    provider = provider or get_embedding_provider()
    dim = embedding_dim if embedding_dim is not None else get_embedding_dim(provider)
    if provider == "ollama":
        return f"medical_assistance_rag_ollama_{dim}"
    return "medical_assistance_rag"


class ThesisEmbeddings(Embeddings):
    """Sync LangChain Embeddings wrapper over async thesis embed helpers."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return asyncio.run(embed_documents(texts))

    def embed_query(self, text: str) -> List[float]:
        return asyncio.run(embed_text(text))


def build_embeddings() -> Embeddings:
    return ThesisEmbeddings()
