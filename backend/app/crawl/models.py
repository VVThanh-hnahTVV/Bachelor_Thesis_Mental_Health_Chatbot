from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

StagingStatus = str  # pending | approved | rejected | indexed


@dataclass(frozen=True)
class CrawlFeed:
    feed_id: str
    url: str
    publisher: str
    language: str
    trust_tier: str
    content_type: str
    country: str = ""


@dataclass
class CrawledArticle:
    source_id: str
    url: str
    canonical_url: str
    title: str
    full_text: str
    publisher: str
    language: str
    trust_tier: str
    content_type: str
    topics: list[str] = field(default_factory=lambda: ["mental_health"])
    published_at: str = ""
    fetched_at: str = ""
    content_hash: str = ""
    feed_id: str = ""
    summary: str = ""
    status: StagingStatus = "pending"
    word_count: int = 0
    relevance_score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    reviewed_at: str = ""
    reviewed_by: str = ""
    indexed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrawledArticle:
        return cls(
            source_id=str(data.get("source_id", "")),
            url=str(data.get("url", "")),
            canonical_url=str(data.get("canonical_url", "")),
            title=str(data.get("title", "")),
            full_text=str(data.get("full_text", "")),
            publisher=str(data.get("publisher", "")),
            language=str(data.get("language", "")),
            trust_tier=str(data.get("trust_tier", "curated")),
            content_type=str(data.get("content_type", "news_article")),
            topics=list(data.get("topics") or ["mental_health"]),
            published_at=str(data.get("published_at") or ""),
            fetched_at=str(data.get("fetched_at") or ""),
            content_hash=str(data.get("content_hash") or ""),
            feed_id=str(data.get("feed_id") or ""),
            summary=str(data.get("summary") or ""),
            status=str(data.get("status") or "pending"),
            word_count=int(data.get("word_count") or 0),
            relevance_score=float(data.get("relevance_score") or 0.0),
            matched_keywords=list(data.get("matched_keywords") or []),
            reviewed_at=str(data.get("reviewed_at") or ""),
            reviewed_by=str(data.get("reviewed_by") or ""),
            indexed_at=str(data.get("indexed_at") or ""),
        )
