from typing import Dict, List, Tuple

from .pubmed_search import PubmedSearchAgent
from .tavily_search import TavilySearchAgent


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
            tavily_results, tavily_sources = self.tavily_search_agent.search_tavily(query=query)
            sections.append(f"=== Tavily (web) ===\n{tavily_results}")
            sources.extend(tavily_sources)

        if self.enable_pubmed:
            pubmed_results, pubmed_sources = self.pubmed_search_agent.search_pubmed(query=query)
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
