from __future__ import annotations

import html
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; HeliosMentalHealthCrawler/0.2; +research) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class RssItem:
    title: str
    link: str
    published_at: str
    description: str


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_pub_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError, OverflowError):
        return raw.strip()


def fetch_rss_items(
    feed_url: str,
    *,
    client: httpx.Client,
    max_items: int = 30,
) -> list[RssItem]:
    response = client.get(feed_url, timeout=30.0)
    response.raise_for_status()
    root = ET.fromstring(response.content)

    items: list[RssItem] = []
    for node in root.iter():
        if _local_name(node.tag) != "item":
            continue

        title = html.unescape((node.findtext("title") or "").strip())
        link = (node.findtext("link") or "").strip()
        if not link:
            for child in node:
                if _local_name(child.tag) == "link" and child.attrib.get("href"):
                    link = child.attrib["href"].strip()
                    break

        if not title or not link:
            continue

        pub = _parse_pub_date(node.findtext("pubDate") or node.findtext("published"))
        description = html.unescape((node.findtext("description") or "").strip())
        items.append(RssItem(title=title, link=link, published_at=pub, description=description))
        if len(items) >= max_items:
            break

    logger.info("Fetched %d RSS items from %s", len(items), feed_url)
    return items
