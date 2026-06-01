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

    def search(self, query: str) -> str:
        """Run enabled search backends and combine results."""
        query = query.strip().strip("\"'")
        sections = []

        if self.enable_tavily:
            tavily_results = self.tavily_search_agent.search_tavily(query=query)
            sections.append(f"=== Tavily (web) ===\n{tavily_results}")

        if self.enable_pubmed:
            pubmed_results = self.pubmed_search_agent.search_pubmed(query=query)
            sections.append(f"=== PubMed (medical literature) ===\n{pubmed_results}")

        if not sections:
            return "Web search is disabled (enable TAVILY or PubMed in configuration)."

        return "\n\n".join(sections)
