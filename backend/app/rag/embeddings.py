from __future__ import annotations

import hashlib
import logging
import math
from typing import Iterable

import httpx
from langchain_openai import OpenAIEmbeddings

from app.config import get_settings

logger = logging.getLogger(__name__)


def _hash_embedding(text: str, dims: int = 128) -> list[float]:
    """Deterministic local fallback used when embedding providers are unavailable."""
    vec = [0.0] * dims
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % dims
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def _ollama_embed_texts(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    base = s.ollama_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{base}/api/embed",
            json={"model": s.embedding_model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
    embeddings = data.get("embeddings")
    if isinstance(embeddings, list) and all(isinstance(item, list) for item in embeddings):
        return [[float(v) for v in item] for item in embeddings]
    embedding = data.get("embedding")
    if len(texts) == 1 and isinstance(embedding, list):
        return [[float(v) for v in embedding]]
    raise RuntimeError("Ollama embedding response did not include embeddings")


async def embed_text(text: str) -> list[float]:
    s = get_settings()
    if s.embedding_provider == "ollama":
        try:
            return (await _ollama_embed_texts([text]))[0]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama embedding failed, using local hash embedding: %s", exc)
    if s.embedding_provider == "openai" and s.openai_api_key:
        try:
            client = OpenAIEmbeddings(
                api_key=s.openai_api_key,
                model=s.embedding_model,
            )
            return await client.aembed_query(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI embedding failed, using local hash embedding: %s", exc)
    return _hash_embedding(text)


async def embed_documents(texts: Iterable[str]) -> list[list[float]]:
    s = get_settings()
    text_list = list(texts)
    if not text_list:
        return []
    if s.embedding_provider == "ollama":
        try:
            return await _ollama_embed_texts(text_list)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama document embedding failed, using local hash embeddings: %s", exc)
    if s.embedding_provider == "openai" and s.openai_api_key:
        try:
            client = OpenAIEmbeddings(
                api_key=s.openai_api_key,
                model=s.embedding_model,
            )
            return await client.aembed_documents(text_list)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI document embedding failed, using local hash embeddings: %s", exc)
    return [_hash_embedding(text) for text in text_list]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    denom = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if denom == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / denom
