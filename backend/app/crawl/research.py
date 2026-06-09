from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.crawl.rss import USER_AGENT

logger = logging.getLogger(__name__)

EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

# Curated mental-health literature queries (Europe PMC syntax).
RESEARCH_QUERIES: tuple[str, ...] = (
    '(depression OR anxiety OR "mental health" OR "mental illness") AND HAS_ABSTRACT:Y',
    '("cognitive behavioral therapy" OR psychotherapy) AND (depression OR anxiety) AND HAS_ABSTRACT:Y',
)


@dataclass(frozen=True)
class ResearchHit:
    title: str
    url: str
    abstract: str
    published_at: str
    publisher: str
    pmid: str
    journal: str


def _parse_epmc_date(raw: str) -> str:
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:19], fmt).replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue
    return raw


def _is_within_max_age(published_at: str, max_age_days: int) -> bool:
    if max_age_days <= 0 or not published_at:
        return True
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    except ValueError:
        return True
    return dt >= datetime.now(UTC) - timedelta(days=max_age_days)


def fetch_research_hits(
    *,
    client: httpx.Client,
    query: str,
    max_results: int = 10,
    max_age_days: int = 1095,
) -> list[ResearchHit]:
    """Search Europe PMC for recent mental-health papers with abstracts."""
    params = {
        "query": query,
        "format": "json",
        "pageSize": min(max_results * 3, 50),
        "resultType": "core",
        "sort": "DATE_DESC",
    }
    response = None
    for attempt in range(2):
        try:
            response = client.get(
                EUROPE_PMC_SEARCH_URL,
                params=params,
                timeout=45.0,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            break
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (503, 429) and attempt == 0:
                logger.info("Europe PMC busy, retrying once...")
                continue
            raise
    assert response is not None
    data = response.json()
    hits_raw: list[dict[str, Any]] = data.get("resultList", {}).get("result", []) or []

    results: list[ResearchHit] = []
    for hit in hits_raw:
        if len(results) >= max_results:
            break

        title = str(hit.get("title") or "").strip()
        abstract = str(hit.get("abstractText") or "").strip()
        if not title or len(abstract) < 120:
            continue

        pmid = str(hit.get("pmid") or hit.get("id") or "").strip()
        journal = str(hit.get("journalTitle") or "Europe PMC").strip()
        pub = _parse_epmc_date(
            str(hit.get("firstPublicationDate") or hit.get("pubYear") or "")
        )
        if pub and not _is_within_max_age(pub, max_age_days):
            continue

        if pmid.isdigit():
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        else:
            source = str(hit.get("source") or "MED")
            url = f"https://europepmc.org/article/{source}/{hit.get('id', '')}"

        results.append(
            ResearchHit(
                title=title,
                url=url,
                abstract=abstract,
                published_at=pub,
                publisher=journal,
                pmid=pmid,
                journal=journal,
            )
        )

    logger.info("Europe PMC query returned %d hits for: %s", len(results), query[:80])
    return results


def crawl_research_articles(
    *,
    client: httpx.Client,
    max_total: int = 8,
    max_age_days: int = 1095,
) -> list[ResearchHit]:
    """Run curated research queries and dedupe by URL."""
    seen_urls: set[str] = set()
    collected: list[ResearchHit] = []
    per_query = max(3, max_total // len(RESEARCH_QUERIES) + 1)

    for query in RESEARCH_QUERIES:
        if len(collected) >= max_total:
            break
        try:
            hits = fetch_research_hits(
                client=client,
                query=query,
                max_results=per_query,
                max_age_days=max_age_days,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Research query failed (%s): %s", query[:60], exc)
            continue

        for hit in hits:
            if hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            collected.append(hit)
            if len(collected) >= max_total:
                break

    return collected
