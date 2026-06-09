from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.crawl.extract import fetch_article_text
from app.crawl.feeds import CRAWL_FEEDS
from app.crawl.keywords import passes_strict_mental_health_filter
from app.crawl.models import CrawledArticle
from app.crawl.research import crawl_research_articles
from app.crawl.rss import USER_AGENT, RssItem, fetch_rss_items
from app.crawl.site_sources import (
    VINMEC_SOURCE,
    WHO_SOURCE,
    fetch_vinmec_candidates,
    fetch_who_mental_health_pages,
)
from app.crawl.staging import DEFAULT_STAGING_DIR, upsert_to_pending

logger = logging.getLogger(__name__)


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def _source_id(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_published_at(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _is_too_old(published_at: str, max_age_days: int) -> bool:
    if max_age_days <= 0:
        return False
    dt = _parse_published_at(published_at)
    if dt is None:
        return False
    return dt < datetime.now(UTC) - timedelta(days=max_age_days)


def _sort_rss_newest_first(items: list[RssItem]) -> list[RssItem]:
    def sort_key(item: RssItem) -> datetime:
        return _parse_published_at(item.published_at) or datetime.min.replace(tzinfo=UTC)

    return sorted(items, key=sort_key, reverse=True)


def _make_summary(text: str, *, max_chars: int = 280) -> str:
    snippet = re.sub(r"\s+", " ", text).strip()
    if len(snippet) <= max_chars:
        return snippet
    return snippet[: max_chars - 1].rstrip() + "…"


def _save_article(
    article: CrawledArticle,
    *,
    staging_path: Path,
) -> tuple[bool, bool]:
    """Returns (added, duplicate)."""
    if upsert_to_pending(article, base_dir=staging_path):
        return True, False
    return False, True


def _ingest_item(
    item: RssItem,
    *,
    feed_id: str,
    publisher: str,
    language: str,
    trust_tier: str,
    content_type: str,
    fetched_at: str,
    staging_path: Path,
    client: httpx.Client,
    max_age_days: int,
    skip_age_check: bool = False,
) -> tuple[str, str | None]:
    """
    Fetch, filter, and stage one article.
    Returns (outcome, error_message) where outcome is added|duplicate|filter|old|short|error.
    """
    if not skip_age_check and _is_too_old(item.published_at, max_age_days):
        return "old", None

    if not passes_strict_mental_health_filter(
        item.title, item.description, content_type=content_type
    )[0]:
        return "filter", None

    canonical = _canonical_url(item.link)
    try:
        full_text = fetch_article_text(
            item.link,
            client=client,
            rss_description=item.description,
        )
    except Exception as exc:  # noqa: BLE001
        return "error", f"{feed_id} {item.link}: {exc}"

    if len(full_text) < 150:
        return "short", f"{feed_id} {item.link}: extracted text too short"

    passed, relevance, keywords = passes_strict_mental_health_filter(
        item.title,
        full_text[:3000],
        content_type=content_type,
    )
    if not passed:
        return "filter", None

    article = CrawledArticle(
        source_id=_source_id(canonical),
        url=item.link,
        canonical_url=canonical,
        title=item.title,
        full_text=full_text,
        publisher=publisher,
        language=language,
        trust_tier=trust_tier,
        content_type=content_type,
        published_at=item.published_at,
        fetched_at=fetched_at,
        content_hash=_content_hash(full_text),
        feed_id=feed_id,
        summary=_make_summary(full_text),
        status="pending",
        word_count=len(full_text.split()),
        relevance_score=round(relevance, 3),
        matched_keywords=keywords,
    )

    was_added, was_dup = _save_article(article, staging_path=staging_path)
    if was_added:
        return "added", None
    if was_dup:
        return "duplicate", None
    return "duplicate", None


def run_crawl(
    *,
    max_per_feed: int = 8,
    max_total: int = 20,
    max_age_days: int = 730,
    include_research: bool = True,
    research_max: int = 8,
    staging_dir: str | Path = DEFAULT_STAGING_DIR,
) -> dict[str, Any]:
    """
    Crawl whitelisted RSS feeds, Vinmec sitemap, WHO guides, and Europe PMC research.
    New articles are appended to pending staging (deduped across all buckets).
    """
    staging_path = Path(staging_dir)
    fetched_at = datetime.now(UTC).isoformat()
    added = 0
    skipped_duplicate = 0
    skipped_filter = 0
    skipped_too_old = 0
    errors: list[str] = []
    feed_stats: list[dict[str, Any]] = []
    research_added = 0
    site_added = 0

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    def _record_outcome(
        outcome: str,
        err: str | None,
        *,
        counters: dict[str, int],
    ) -> None:
        nonlocal skipped_duplicate, skipped_filter, skipped_too_old
        if outcome == "added":
            counters["kept"] += 1
        elif outcome == "duplicate":
            skipped_duplicate += 1
        elif outcome == "filter":
            skipped_filter += 1
        elif outcome == "old":
            skipped_too_old += 1
        elif outcome in ("short", "error"):
            counters["errors"] += 1
            if err:
                errors.append(err)

    with httpx.Client(headers=headers, follow_redirects=True) as client:
        # Official site sources first (WHO + Vinmec) before RSS fills the quota.
        site_jobs: list[tuple[Any, list[RssItem], bool, int]] = [
            (WHO_SOURCE, fetch_who_mental_health_pages(), True, max_per_feed),
        ]
        try:
            vinmec_items = fetch_vinmec_candidates(
                client=client,
                max_total=min(6, max_total),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"vinmec_sitemap: {exc}")
            vinmec_items = []
        site_jobs.append((VINMEC_SOURCE, vinmec_items, False, max_per_feed))

        for source, items, skip_age, per_source_cap in site_jobs:
            if added >= max_total:
                break
            counters = {"kept": 0, "errors": 0}
            for item in items:
                if added >= max_total or counters["kept"] >= per_source_cap:
                    break
                outcome, err = _ingest_item(
                    item,
                    feed_id=source.source_id,
                    publisher=source.publisher,
                    language=source.language,
                    trust_tier=source.trust_tier,
                    content_type=source.content_type,
                    fetched_at=fetched_at,
                    staging_path=staging_path,
                    client=client,
                    max_age_days=max_age_days,
                    skip_age_check=skip_age,
                )
                if outcome == "added":
                    added += 1
                    site_added += 1
                _record_outcome(outcome, err, counters=counters)
            feed_stats.append(
                {
                    "feed_id": source.source_id,
                    "publisher": source.publisher,
                    "kept": counters["kept"],
                    "errors": counters["errors"],
                }
            )

        for feed in CRAWL_FEEDS:
            if added >= max_total:
                break

            counters = {"kept": 0, "errors": 0}

            try:
                items = fetch_rss_items(
                    feed.url,
                    client=client,
                    max_items=max(max_per_feed * 25, 120),
                )
            except Exception as exc:  # noqa: BLE001
                msg = f"{feed.feed_id}: RSS fetch failed — {exc}"
                logger.error(msg)
                errors.append(msg)
                feed_stats.append(
                    {"feed_id": feed.feed_id, "kept": 0, "errors": 1}
                )
                continue

            items = _sort_rss_newest_first(items)
            candidates = [
                item
                for item in items
                if passes_strict_mental_health_filter(
                    item.title, item.description, content_type=feed.content_type
                )[0]
            ]

            for item in candidates:
                if added >= max_total or counters["kept"] >= max_per_feed:
                    break

                outcome, err = _ingest_item(
                    item,
                    feed_id=feed.feed_id,
                    publisher=feed.publisher,
                    language=feed.language,
                    trust_tier=feed.trust_tier,
                    content_type=feed.content_type,
                    fetched_at=fetched_at,
                    staging_path=staging_path,
                    client=client,
                    max_age_days=max_age_days,
                )
                if outcome == "added":
                    added += 1
                _record_outcome(outcome, err, counters=counters)

            feed_stats.append(
                {
                    "feed_id": feed.feed_id,
                    "publisher": feed.publisher,
                    "kept": counters["kept"],
                    "errors": counters["errors"],
                }
            )

        if include_research and added < max_total:
            research_budget = min(research_max, max_total - added)
            try:
                hits = crawl_research_articles(
                    client=client,
                    max_total=research_budget,
                    max_age_days=max(max_age_days, 365),
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"research: {exc}")
                hits = []

            for hit in hits:
                full_text = f"{hit.title}\n\n{hit.abstract}"
                passed, relevance, keywords = passes_strict_mental_health_filter(
                    hit.title,
                    hit.abstract,
                    content_type="research_article",
                )
                if not passed:
                    skipped_filter += 1
                    continue

                canonical = _canonical_url(hit.url)
                article = CrawledArticle(
                    source_id=_source_id(canonical),
                    url=hit.url,
                    canonical_url=canonical,
                    title=hit.title,
                    full_text=full_text,
                    publisher=hit.publisher,
                    language="en",
                    trust_tier="official",
                    content_type="research_article",
                    published_at=hit.published_at,
                    fetched_at=fetched_at,
                    content_hash=_content_hash(full_text),
                    feed_id="europe_pmc_research",
                    summary=_make_summary(hit.abstract),
                    status="pending",
                    word_count=len(full_text.split()),
                    relevance_score=round(relevance, 3),
                    matched_keywords=keywords,
                )
                was_added, was_dup = _save_article(article, staging_path=staging_path)
                if was_added:
                    added += 1
                    research_added += 1
                elif was_dup:
                    skipped_duplicate += 1

    return {
        "success": True,
        "added_to_pending": added,
        "research_added": research_added,
        "site_added": site_added,
        "skipped_duplicate": skipped_duplicate,
        "skipped_filter": skipped_filter,
        "skipped_too_old": skipped_too_old,
        "feed_stats": feed_stats,
        "errors": errors,
    }
