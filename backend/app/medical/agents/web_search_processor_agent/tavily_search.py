import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
VALID_SEARCH_DEPTHS = frozenset({"ultra-fast", "fast", "basic", "advanced"})
_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)
_QUERY_PREAMBLE_PATTERNS = (
    r"^here is\s+(?:the\s+)?(?:query|question)\s*:?\s*",
    r"^(?:the\s+)?(?:search\s+)?(?:query|question)\s*:?\s*",
    r"^summarized\s+(?:search\s+)?(?:query|question)\s*:?\s*",
)


def _strip_query_preamble(line: str) -> str:
    text = line.strip()
    for pattern in _QUERY_PREAMBLE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    return text


def _normalize_tavily_results(raw: Any) -> List[Dict[str, Any]]:
    """Accept list[dict], dict wrapper, JSON string, or error string from Tavily."""
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("{") or text.startswith("["):
            try:
                return _normalize_tavily_results(json.loads(text))
            except json.JSONDecodeError:
                pass
        return [
            {
                "title": "Tavily",
                "url": "N/A",
                "score": "N/A",
                "content": text,
            }
        ]
    if isinstance(raw, dict):
        if "results" in raw and isinstance(raw["results"], list):
            return _normalize_tavily_results(raw["results"])
        return [raw]
    if isinstance(raw, list):
        normalized: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str):
                normalized.append(
                    {
                        "title": "N/A",
                        "url": "N/A",
                        "score": "N/A",
                        "content": item,
                    }
                )
            else:
                normalized.append(
                    {
                        "title": "N/A",
                        "url": "N/A",
                        "score": "N/A",
                        "content": str(item),
                    }
                )
        return normalized
    return [
        {
            "title": "N/A",
            "url": "N/A",
            "score": "N/A",
            "content": str(raw),
        }
    ]


def _format_tavily_hit(res: Dict[str, Any]) -> str:
    return (
        f"title: {res.get('title', 'N/A')}\n"
        f"url: {res.get('url', 'N/A')}\n"
        f"score: {res.get('score', 'N/A')}\n"
        f"content: {res.get('content', '')}"
    )


def _extract_tavily_sources(search_docs: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Pull citable {title, path} pairs from Tavily hits (skip placeholders/dupes)."""
    sources: List[Dict[str, str]] = []
    seen: set[str] = set()
    for res in search_docs:
        url = str(res.get("url") or "").strip()
        if not url or url == "N/A" or not url.lower().startswith("http"):
            continue
        if url in seen:
            continue
        seen.add(url)
        title = str(res.get("title") or "").strip() or url
        sources.append({"title": title, "path": url})
    return sources


def sanitize_tavily_query(query: str, *, max_len: int = 400) -> str:
    """Strip LLM fluff; Tavily returns 400 on empty query."""
    text = (query or "").strip().strip("\"'`")
    if not text:
        return ""
    lines = [
        ln.strip().lstrip("-•* ").strip()
        for ln in text.splitlines()
        if ln.strip()
    ]
    candidates: List[str] = []
    for ln in lines:
        cleaned = _strip_query_preamble(ln)
        if len(cleaned) >= 3:
            candidates.append(cleaned)
    if candidates:
        text = max(candidates, key=len)
    elif lines:
        text = max(lines, key=len)
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] or text[:max_len]
    return text


def _filter_domains(domains: List[str]) -> List[str]:
    valid: List[str] = []
    for raw in domains:
        d = raw.strip().lower()
        if d.startswith("http://"):
            d = d[7:]
        if d.startswith("https://"):
            d = d[8:]
        d = d.split("/")[0]
        if _DOMAIN_RE.match(d):
            valid.append(d)
        else:
            logger.warning("Skipping invalid Tavily include_domain: %r", raw)
    return valid


class TavilySearchAgent:
    """General web search via Tavily API."""

    def __init__(
        self,
        max_results: int = 5,
        include_domains: Optional[List[str]] = None,
        search_depth: str = "advanced",
        api_key: Optional[str] = None,
    ):
        self.max_results = max(1, min(int(max_results), 20))
        self.include_domains = _filter_domains(include_domains or [])
        depth = (search_depth or "advanced").strip().lower()
        self.search_depth = depth if depth in VALID_SEARCH_DEPTHS else "advanced"
        if depth not in VALID_SEARCH_DEPTHS:
            logger.warning(
                "Invalid TAVILY_SEARCH_DEPTH=%r; using 'advanced'", search_depth
            )
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")

    def search_tavily(self, query: str) -> Tuple[str, List[Dict[str, str]]]:
        """Perform a web search using Tavily API.

        Returns a tuple of (formatted_text_for_llm, citable_sources).
        ``citable_sources`` is a list of ``{"title", "path"}`` dicts so the
        graph can append reference links the same way RAG does.
        """
        query = sanitize_tavily_query(query)
        if not query:
            return "No web search query provided.", []

        if not self.api_key:
            return "Tavily search skipped: set TAVILY_API_KEY in backend/.env", []

        payload: Dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "max_results": self.max_results,
            "search_depth": self.search_depth,
        }
        if self.include_domains:
            payload["include_domains"] = self.include_domains

        try:
            response = requests.post(TAVILY_API_URL, json=payload, timeout=30)
            if not response.ok:
                detail = response.text[:400]
                logger.warning(
                    "Tavily HTTP %s for query=%r: %s",
                    response.status_code,
                    query[:80],
                    detail,
                )
                return f"Error retrieving web search results: {detail}", []

            raw_results = response.json()
            search_docs = _normalize_tavily_results(raw_results.get("results", []))
            if search_docs:
                text = "\n\n---\n\n".join(_format_tavily_hit(res) for res in search_docs)
                return text, _extract_tavily_sources(search_docs)
            return "No relevant Tavily results found.", []
        except Exception as e:
            logger.warning("Tavily search failed for query=%r: %s", query[:80], e)
            return f"Error retrieving web search results: {e}", []
