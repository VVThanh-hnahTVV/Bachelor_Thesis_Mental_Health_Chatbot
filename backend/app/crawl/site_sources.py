from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from bs4 import BeautifulSoup

from app.crawl.rss import RssItem

logger = logging.getLogger(__name__)

VINMEC_SITEMAP_INDEX = "https://www.vinmec.com/sitemap.xml"
VINMEC_SLUG_HINTS: tuple[str, ...] = (
    "tram-cam",
    "tam-than",
    "tam-ly",
    "lo-au",
    "stress",
    "tu-tu",
    "tu-hai",
    "benh-tam-than",
    "roi-loan-tam-than",
    "tam-ly-hoc",
    "psych",
    "depression",
    "anxiety",
)

WHO_MENTAL_HEALTH_PAGES: tuple[tuple[str, str], ...] = (
    ("Mental health at work", "https://www.who.int/news-room/fact-sheets/detail/mental-health-at-work"),
    (
        "Mental health in emergencies",
        "https://www.who.int/news-room/fact-sheets/detail/mental-health-in-emergencies",
    ),
    (
        "Mental health of adolescents",
        "https://www.who.int/news-room/fact-sheets/detail/adolescent-mental-health",
    ),
    (
        "Mental health of older adults",
        "https://www.who.int/news-room/fact-sheets/detail/mental-health-of-older-adults",
    ),
    (
        "Refugee and migrant mental health",
        "https://www.who.int/news-room/fact-sheets/detail/refugee-and-migrant-mental-health",
    ),
    (
        "Depression",
        "https://www.who.int/news-room/fact-sheets/detail/depression",
    ),
    (
        "Suicide",
        "https://www.who.int/news-room/fact-sheets/detail/suicide",
    ),
    (
        "Schizophrenia",
        "https://www.who.int/news-room/fact-sheets/detail/schizophrenia",
    ),
)


@dataclass(frozen=True)
class SiteSource:
    source_id: str
    publisher: str
    language: str
    trust_tier: str
    content_type: str
    country: str


VINMEC_SOURCE = SiteSource(
    source_id="vinmec_sitemap",
    publisher="Vinmec",
    language="vi",
    trust_tier="official",
    content_type="health_guide",
    country="VN",
)

WHO_SOURCE = SiteSource(
    source_id="who_mental_health",
    publisher="WHO",
    language="en",
    trust_tier="official",
    content_type="health_guide",
    country="INT",
)


def _parse_iso_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError, OverflowError):
        return raw.strip()


def _page_title(url: str, client: httpx.Client) -> str:
    response = client.get(url, timeout=35.0)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    h1 = soup.find("h1")
    if h1 is not None:
        text = h1.get_text(" ", strip=True)
        if text:
            return text
    title = soup.find("title")
    if title is not None:
        return title.get_text(" ", strip=True).split("|")[0].strip()
    return ""


def _vinmec_post_sitemaps(client: httpx.Client, *, max_files: int = 4) -> list[str]:
    response = client.get(VINMEC_SITEMAP_INDEX, timeout=30.0)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    locs = [el.text for el in root.iter() if el.tag.endswith("loc")]
    post_maps = sorted(
        [loc for loc in locs if loc and "/sitemap/posts-vi-" in loc],
        reverse=True,
    )
    return post_maps[:max_files]


def _vinmec_slug_matches(url: str) -> bool:
    lowered = url.lower()
    return any(hint in lowered for hint in VINMEC_SLUG_HINTS)


def fetch_vinmec_candidates(
    *,
    client: httpx.Client,
    max_total: int = 8,
) -> list[RssItem]:
    """Discover recent Vinmec mental-health articles via sitemap (no public RSS)."""
    candidates: list[RssItem] = []
    seen_urls: set[str] = set()

    try:
        sitemap_urls = _vinmec_post_sitemaps(client)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vinmec sitemap index failed: %s", exc)
        return []

    for sitemap_url in sitemap_urls:
        if len(candidates) >= max_total:
            break
        try:
            response = client.get(sitemap_url, timeout=35.0)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vinmec sitemap %s failed: %s", sitemap_url, exc)
            continue

        for url_node in root.iter():
            if not url_node.tag.endswith("url"):
                continue
            loc = ""
            lastmod = ""
            for child in url_node:
                if child.tag.endswith("loc"):
                    loc = (child.text or "").strip()
                elif child.tag.endswith("lastmod"):
                    lastmod = (child.text or "").strip()
            if not loc or loc in seen_urls or not _vinmec_slug_matches(loc):
                continue
            seen_urls.add(loc)
            candidates.append(
                RssItem(
                    title=loc.rstrip("/").rsplit("/", 1)[-1].replace("-", " "),
                    link=loc,
                    published_at=_parse_iso_date(lastmod),
                    description="",
                )
            )
            if len(candidates) >= max_total * 3:
                break

    candidates.sort(key=lambda item: item.published_at or "", reverse=True)
    enriched: list[RssItem] = []
    for item in candidates:
        if len(enriched) >= max_total:
            break
        try:
            title = _page_title(item.link, client)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Vinmec title fetch failed %s: %s", item.link, exc)
            continue
        if not title:
            continue
        enriched.append(
            RssItem(
                title=title,
                link=item.link,
                published_at=item.published_at,
                description="",
            )
        )
    logger.info("Vinmec sitemap: %d mental-health candidates", len(enriched))
    return enriched


def fetch_who_mental_health_pages() -> list[RssItem]:
    """Curated WHO mental-health fact sheets (stable, high-trust)."""
    now = datetime.now(UTC).isoformat()
    return [
        RssItem(
            title=title,
            link=url,
            published_at=now,
            description=title,
        )
        for title, url in WHO_MENTAL_HEALTH_PAGES
    ]
