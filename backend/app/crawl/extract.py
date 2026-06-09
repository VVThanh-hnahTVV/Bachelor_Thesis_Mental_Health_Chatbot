from __future__ import annotations

import logging
import re
from html import unescape
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.crawl.rss import USER_AGENT

logger = logging.getLogger(__name__)

_SITE_SELECTORS: dict[str, tuple[str, ...]] = {
    "vnexpress.net": (".fck_detail", "article.fck_detail", "article"),
    "thanhnien.vn": (".detail-content", "article.detail-content", "article"),
    "suckhoedoisong.vn": (".detail-content", ".content-detail", "article"),
    "cdc.gov": ("main", "#content", "article"),
    "vinmec.com": (".article-content", ".content-detail", ".post-content", "article"),
    "who.int": ("main", ".sf-content-block", "article", "#content"),
    "sciencedaily.com": ("div#text", "#text", "article"),
    "theguardian.com": ("article", ".article-body-commercial-selector", "main"),
    "medlineplus.gov": ("#topic-summary", "#mplus-content", "main"),
    "nimh.nih.gov": ("main", "#content", "article"),
}

_STRIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript"}


def _hostname(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _selectors_for_url(url: str) -> tuple[str, ...]:
    host = _hostname(url)
    for domain, selectors in _SITE_SELECTORS.items():
        if host == domain or host.endswith("." + domain):
            return selectors
    return ("article", "main", "#content", ".content")


def _clean_text(element) -> str:
    for tag in element.find_all(_STRIP_TAGS):
        tag.decompose()

    blocks: list[str] = []
    for node in element.find_all(["p", "li", "h2", "h3", "h4"]):
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if len(text) >= 40:
            blocks.append(text)

    if blocks:
        return "\n\n".join(blocks)

    return re.sub(r"\n{3,}", "\n\n", element.get_text("\n", strip=True)).strip()


def _description_fallback(description: str) -> str:
    if not description:
        return ""
    soup = BeautifulSoup(description, "html.parser")
    text = _clean_text(soup)
    if text:
        return text
    return unescape(re.sub(r"<[^>]+>", " ", description)).strip()


def fetch_article_text(
    url: str,
    *,
    client: httpx.Client,
    rss_description: str = "",
) -> str:
    try:
        response = client.get(url, timeout=40.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.debug("Article not found (404), using RSS fallback: %s", url)
        else:
            logger.warning("Failed to fetch %s: %s", url, exc)
        return _description_fallback(rss_description)
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return _description_fallback(rss_description)

    soup = BeautifulSoup(response.text, "html.parser")
    for selector in _selectors_for_url(url):
        element = soup.select_one(selector)
        if element is None:
            continue
        text = _clean_text(element)
        if len(text) >= 200:
            return text

    body = soup.find("body")
    if body is not None:
        text = _clean_text(body)
        if len(text) >= 200:
            return text

    return _description_fallback(rss_description)
