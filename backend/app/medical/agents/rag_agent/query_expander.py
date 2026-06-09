import logging
from typing import List, Dict, Any

class QueryExpander:
    """
    Expands user queries with medical terminology to improve retrieval.
    """
    def __init__(self, config):
        self.logger = logging.getLogger(f"{self.__module__}")
        self.config = config
        self.model = config.rag.llm
        
    def expand_query(self, original_query: str) -> Dict[str, Any]:
        """
        Expand the original query with relevant medical terms.
        
        Args:
            original_query: The user's original query
            
        Returns:
            Dictionary with original and expanded queries
        """
        self.logger.info(f"Expanding query: {original_query}")
        
        # Generate expansions - implement one of the strategies below
        expanded_query = self._generate_expansions(original_query)
        
        return {
            "original_query": original_query,
            "expanded_query": expanded_query.content
        }
    
    def _generate_expansions(self, query: str) -> str:
        """Use LLM to expand query with medical terminology."""
        prompt = f"""
        As a medical expert, expand the following query with relevant medical terminology,
        synonyms, and related concepts that would help retrieve relevant medical information.

        User Query: {query}

        Rules:
        - Expand only if needed; otherwise return the user query unchanged.
        - Stay specific to the medical domain in the query; do not add unrelated domains.
        - Keep the expanded query in English for retrieval (even if the user wrote in another language).
        - If the user asks for a tabular answer format, mention that in the expanded query; do not produce a table yourself.
        - Output only the expanded query text with no explanations.
        """
        expansion = self.model.invoke(prompt)
        
        return expansion