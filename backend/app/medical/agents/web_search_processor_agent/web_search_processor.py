import os
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from app.medical.prompts import MARKDOWN_RESPONSE_INSTRUCTIONS
from .tavily_search import sanitize_tavily_query
from .web_search_agent import WebSearchAgent

load_dotenv()

_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _web_search_time_context() -> str:
    """Human-readable current time for search prompts (Vietnam local time)."""
    now = datetime.now(_VN_TZ)
    return (
        f"Current date and time (Vietnam): {now.strftime('%d/%m/%Y %H:%M')} "
        f"({now.strftime('%A')}, year {now.year})"
    )


def _web_search_time_instructions(*, for_query_rewrite: bool) -> str:
    time_ctx = _web_search_time_context()
    if for_query_rewrite:
        return f"""Time context:
{time_ctx}

Time rules for the search query:
- If the user did NOT specify a time period, assume they want the most recent information as of the current date above.
- Include the current year or words like "latest", "mới nhất", "hiện tại" in the search query when the topic is news, outbreaks, epidemics, or "thời điểm hiện tại".
- If the user explicitly mentions a time (e.g. 2020, "năm ngoái", "tháng trước"), use that period instead of the current date.
"""
    return f"""Time context:
{time_ctx}

Time rules for your answer:
- If the user did NOT specify a time period, frame the response as information current as of the date above.
- Prefer sources that match the requested time window; say clearly if results are older or not time-specific.
- If the user explicitly asked about another period, answer for that period only.
"""

class WebSearchProcessor:
    """
    Processes web search results and routes them to the appropriate LLM for response generation.
    """
    
    def __init__(self, config):
        self.web_search_agent = WebSearchAgent(config)
        
        # Initialize LLM for processing web search results
        self.llm = config.web_search.llm
    
    def _build_prompt_for_web_search(self, query: str, chat_history: Optional[str] = None) -> str:
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
        prompt = f"""Conversation memory (summary + recent user questions):

        {chat_history or "(none yet)"}

        The user asked the following question:

        {query}

        {_web_search_time_instructions(for_query_rewrite=True)}
        Summarize them into a single, well-formed search query only if the past conversation seems relevant.
        Reply with ONLY the search query text (one line, no quotes, no preamble like "Here is the query:").
        Keep it concise (under 200 characters) and capture the key medical intent.
        """
        print("Web Search Query Prompt:", prompt)

        return prompt
    
    def process_web_results(self, query: str, chat_history: Optional[str] = None) -> str:
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

        print(f"[WebSearchProcessor] Fetched results: {web_results}")
        
        # Construct prompt to LLM for processing the results
        llm_prompt = (
            "You are an AI assistant specialized in medical information. Below are search results "
            "from Tavily (general web) and/or PubMed (peer-reviewed medical literature). "
            "Summarize and generate a helpful, concise response. "
            "Prefer PubMed evidence when available. Cite source URLs or PMIDs when relevant. "
            "Do not diagnose or prescribe; recommend professional care for serious concerns.\n\n"
            f"{_web_search_time_instructions(for_query_rewrite=False)}\n"
            f"{MARKDOWN_RESPONSE_INSTRUCTIONS}\n\n"
            f"Query: {query}\n\nSearch Results:\n{web_results}\n\nResponse:"
        )
        
        # Invoke the LLM to process the results
        response = self.llm.invoke(llm_prompt)
        return response.content if hasattr(response, "content") else str(response)
