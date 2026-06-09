from typing import Any, Optional

from .web_search_processor import WebSearchProcessor


class WebSearchProcessorAgent:
    """
    Agent responsible for processing web search results and routing them to the appropriate LLM for response generation.
    """
    
    def __init__(self, config):
        self.web_search_processor = WebSearchProcessor(config)
    
    def process_web_search_results(
        self, query: str, chat_history: Optional[str] = None
    ) -> dict[str, Any]:
        """Processes web search results and returns answer + suggest_activities flag."""
        return self.web_search_processor.process_web_results(query, chat_history)