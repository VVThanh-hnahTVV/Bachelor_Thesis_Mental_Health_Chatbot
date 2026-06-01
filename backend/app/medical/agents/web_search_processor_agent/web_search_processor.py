import os
from typing import Dict, List, Optional

from dotenv import load_dotenv

from app.medical.prompts import MARKDOWN_RESPONSE_INSTRUCTIONS
from .tavily_search import sanitize_tavily_query
from .web_search_agent import WebSearchAgent

load_dotenv()

class WebSearchProcessor:
    """
    Processes web search results and routes them to the appropriate LLM for response generation.
    """
    
    def __init__(self, config):
        self.web_search_agent = WebSearchAgent(config)
        
        # Initialize LLM for processing web search results
        self.llm = config.web_search.llm
    
    def _build_prompt_for_web_search(self, query: str, chat_history: List[Dict[str, str]] = None) -> str:
        """
        Build the prompt for the web search.
        
        Args:
            query: User query
            chat_history: chat history
            
        Returns:
            Complete prompt string
        """
        # Add chat history if provided
        # print("Chat History:", chat_history)
            
        # Build the prompt
        prompt = f"""Here are the last few messages from our conversation:

        {chat_history}

        The user asked the following question:

        {query}

        Summarize them into a single, well-formed search query only if the past conversation seems relevant.
        Reply with ONLY the search query text (one line, no quotes, no preamble like "Here is the query:").
        Keep it concise (under 200 characters) and capture the key medical intent.
        """

        return prompt
    
    def process_web_results(self, query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Fetches web search results, processes them using LLM, and returns a user-friendly response.
        """
        # print(f"[WebSearchProcessor] Fetching web search results for: {query}")
        web_search_query_prompt = self._build_prompt_for_web_search(query=query, chat_history=chat_history)
        # print("Web Search Query Prompt:", web_search_query_prompt)
        web_search_query = self.llm.invoke(web_search_query_prompt)
        llm_text = (
            web_search_query.content
            if hasattr(web_search_query, "content")
            else str(web_search_query)
        )
        search_query = sanitize_tavily_query(llm_text)
        if len(search_query) < 3:
            search_query = sanitize_tavily_query(query)
        if len(search_query) < 3:
            return (
                "I could not form a valid web search query from your message. "
                "Please rephrase your question."
            )

        web_results = self.web_search_agent.search(search_query)

        # print(f"[WebSearchProcessor] Fetched results: {web_results}")
        
        # Construct prompt to LLM for processing the results
        llm_prompt = (
            "You are an AI assistant specialized in medical information. Below are search results "
            "from Tavily (general web) and/or PubMed (peer-reviewed medical literature). "
            "Summarize and generate a helpful, concise response. "
            "Prefer PubMed evidence when available. Cite source URLs or PMIDs when relevant. "
            "Do not diagnose or prescribe; recommend professional care for serious concerns.\n\n"
            f"{MARKDOWN_RESPONSE_INSTRUCTIONS}\n\n"
            f"Query: {query}\n\nSearch Results:\n{web_results}\n\nResponse:"
        )
        
        # Invoke the LLM to process the results
        response = self.llm.invoke(llm_prompt)
        return response.content if hasattr(response, "content") else str(response)
