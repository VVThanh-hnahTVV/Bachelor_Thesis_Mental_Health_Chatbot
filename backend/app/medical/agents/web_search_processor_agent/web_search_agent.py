from typing import Dict, List, Tuple
from urllib.parse import urlparse

from app.chat_progress import emit_progress

from .pubmed_search import PubmedSearchAgent
from .tavily_search import TavilySearchAgent


def _domain_from_url(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or url
    except Exception:
        return url


def _format_domain_list(domains: List[str], *, limit: int = 4) -> str:
    if not domains:
        return ""
    shown = ", ".join(domains[:limit])
    if len(domains) > limit:
        shown += f" (+{len(domains) - limit})"
    return shown


def _format_found_sources(sources: List[Dict[str, str]], *, limit: int = 5) -> str | None:
    seen: set[str] = set()
    domains: List[str] = []
    for src in sources:
        path = str(src.get("path") or "").strip()
        if not path:
            continue
        domain = _domain_from_url(path)
        if domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)
        if len(domains) >= limit:
            break
    return ", ".join(domains) if domains else None


def _tavily_scope_detail(query: str, domains: List[str]) -> str:
    scope = _format_domain_list(domains)
    if scope:
        return f"{scope} · \"{query}\""
    return f"\"{query}\""


class WebSearchAgent:
    """
    Retrieves real-time information from Tavily (general web) and PubMed (medical literature).
    """

    def __init__(self, config):
        ws = config.web_search
        self.enable_tavily = ws.enable_tavily
        self.enable_pubmed = ws.enable_pubmed

        self.tavily_search_agent = TavilySearchAgent(
            max_results=ws.tavily_max_results,
            include_domains=ws.tavily_include_domains,
            search_depth=ws.tavily_search_depth,
            api_key=ws.tavily_api_key,
        )
        self.pubmed_search_agent = PubmedSearchAgent(
            esearch_url=ws.pubmed_esearch_url,
            efetch_url=ws.pubmed_efetch_url,
            max_results=ws.pubmed_max_results,
            tool=ws.pubmed_tool,
            email=ws.pubmed_email,
            api_key=ws.pubmed_api_key,
            enable_europepmc_fallback=ws.pubmed_europepmc_fallback,
            use_ncbi=ws.pubmed_use_ncbi,
        )

    def search(self, query: str) -> Tuple[str, List[Dict[str, str]]]:
        """Run enabled search backends and combine results.

        Returns ``(formatted_text_for_llm, citable_sources)`` where
        ``citable_sources`` is a deduplicated list of ``{"title", "path"}``
        dicts gathered from every enabled backend.
        """
        query = query.strip().strip("\"'")
        sections = []
        sources: List[Dict[str, str]] = []

        if self.enable_tavily:
            emit_progress(
                "web_search_tavily",
                detail=_tavily_scope_detail(
                    query, self.tavily_search_agent.include_domains
                ),
            )
            tavily_results, tavily_sources = self.tavily_search_agent.search_tavily(query=query)
            tavily_found = _format_found_sources(tavily_sources)
            if tavily_found:
                emit_progress("web_search_found", detail=tavily_found)
            sections.append(f"=== Tavily (web) ===\n{tavily_results}")
            sources.extend(tavily_sources)

        if self.enable_pubmed:
            emit_progress("web_search_pubmed", detail=f'PubMed · "{query}"')
            pubmed_results, pubmed_sources = self.pubmed_search_agent.search_pubmed(query=query)
            pubmed_found = _format_found_sources(pubmed_sources)
            if pubmed_found:
                emit_progress("web_search_found", detail=pubmed_found)
            sections.append(f"=== PubMed (medical literature) ===\n{pubmed_results}")
            sources.extend(pubmed_sources)

        if not sections:
            return (
                "Web search is disabled (enable TAVILY or PubMed in configuration).",
                [],
            )

        deduped: List[Dict[str, str]] = []
        seen: set[str] = set()
        for src in sources:
            path = str(src.get("path") or "").strip()
            if not path or path in seen:
                continue
            seen.add(path)
            deduped.append(src)

        return "\n\n".join(sections), deduped
