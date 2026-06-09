import json
from pathlib import Path

from app.crawl.models import CrawledArticle
from app.crawl.staging import (
    get_article,
    list_articles,
    move_article,
    upsert_to_pending,
)


def _article(source_id: str, title: str) -> CrawledArticle:
    return CrawledArticle(
        source_id=source_id,
        url=f"https://example.com/{source_id}",
        canonical_url=f"https://example.com/{source_id}",
        title=title,
        full_text="Body text about depression and anxiety support " * 20,
        publisher="Test",
        language="en",
        trust_tier="curated",
        content_type="news_article",
        summary="preview",
        content_hash=f"hash-{source_id}",
    )


def test_staging_upsert_and_move(tmp_path: Path):
    base = tmp_path / "staging"
    base.mkdir()
    for name in ("pending", "approved", "rejected", "indexed"):
        (base / f"{name}.json").write_text(
            json.dumps({"updated_at": "", "articles": []}),
            encoding="utf-8",
        )

    a1 = _article("abc123", "Mental health news")
    assert upsert_to_pending(a1, base_dir=base) is True
    assert upsert_to_pending(a1, base_dir=base) is False

    pending = list_articles("pending", base_dir=base)
    assert len(pending) == 1

    moved = move_article(
        "abc123",
        from_status="pending",
        to_status="approved",
        base_dir=base,
        reviewed_by="admin-id",
    )
    assert moved is not None
    assert moved.status == "approved"
    assert get_article("abc123", base_dir=base).status == "approved"
