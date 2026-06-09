import logging
from typing import List, Dict, Any, Optional, Union

from app.medical.agents.structured_output import (
    ACTIVITIES_INTRO_RULES,
    SUGGEST_ACTIVITIES_RULES,
    merge_activities_intro,
    parse_rag_output,
    rag_format_instructions,
)
from app.medical.prompts import MARKDOWN_RESPONSE_INSTRUCTIONS

class ResponseGenerator:
    """
    Generates responses based on retrieved context and user query.
    """
    def __init__(self, config):
        """
        Initialize the response generator.
        
        Args:
            config: Configuration object
            llm: Large language model for response generation
        """
        self.logger = logging.getLogger(__name__)
        self.response_generator_model = config.rag.response_generator_model
        self.include_sources = getattr(config.rag, "include_sources", True)

    def _build_prompt(
            self,
            query: str, 
            context: str,
            chat_history: Optional[str] = None,
        ) -> str:
        """
        Build the prompt for the language model.
        
        Args:
            query: User query
            context: Formatted context from retrieved documents
            chat_history: Optional chat history
            
        Returns:
            Complete prompt string
        """

        table_instructions = """
        Some of the retrieved information is presented in table format. When using information from tables:
        1. Present tabular data using proper markdown table formatting with headers, like this:
            | Column1 | Column2 | Column3 |
            |---------|---------|---------|
            | Value1  | Value2  | Value3  |
        2. Re-format the table structure to make it easier to read and understand
        3. If any new component is introduced during re-formatting of the table, mention it explicitly
        4. Clearly interpret the tabular data in your response
        5. Reference the relevant table when presenting specific data points
        6. If appropriate, summarize trends or patterns shown in the tables
        7. If only reference numbers are mentioned and you can fetch the corresponding values like research paper title or authors from the context, replace the reference numbers with the actual values
        """

        response_format_instructions = f"""Instructions:
        1. Answer the query based ONLY on the information provided in the context.
        2. If the context cannot fully answer the query, still write the best partial answer you can in "answer", and set "web_search" to true.
        3. Do not use prior knowledge not contained in the context.
        4. Be concise and accurate.
        5. Only provide sections that are meaningful to have in a chatbot reply. Do not add a separate references section in "answer".
        6. If values are involved, use only values present in context. Do not make up values.
        7. Do not repeat the question in the answer.

        {SUGGEST_ACTIVITIES_RULES}

        {ACTIVITIES_INTRO_RULES}

        ### web_search
        Set to true when the retrieved context is missing key information the user asked for (treatments, mechanisms,
        guidelines, etc.) and a broader web search would likely help. Set to false when the context fully answers the question.

        {MARKDOWN_RESPONSE_INSTRUCTIONS}

        Respond with JSON only (no markdown fences):
        {rag_format_instructions()}"""
            
        # Build the prompt
        prompt = f"""You are a medical assistant providing accurate information based on verified medical sources.

        Conversation memory (summary + recent user questions):
        
        {chat_history or "(none yet)"}

        The user has asked the following question:
        {query}

        I've retrieved the following information to help answer this question:

        {context}

        {table_instructions}

        {response_format_instructions}

        Based on the provided information, answer the user's question and set web_search / suggest_activities accordingly.

        Do not include source links inside the JSON "answer" field. Sources are appended separately by the system."""

        return prompt

    def generate_response(
            self,
            query: str,
            retrieved_docs: List[Dict[str, Any]],
            picture_paths: List[str],
            chat_history: Optional[str] = None,
        ) -> Dict[str, Any]:
        """
        Generate a response based on retrieved documents.
        
        Args:
            query: User query
            retrieved_docs: List of retrieved document dictionaries
            chat_history: Optional chat history
            
        Returns:
            Dict containing response text and source information
        """
        try:
           
            # Extract content from documents for context
            doc_texts = [doc["content"] for doc in retrieved_docs]
            
            # Combine retrieved documents into a single context
            context = "\n\n===DOCUMENT SECTION===\n\n".join(doc_texts)
            
            # Build the prompt
            prompt = self._build_prompt(query, context, chat_history)
            
            # Generate structured response
            raw_response = self.response_generator_model.invoke(prompt)
            structured = parse_rag_output(raw_response)
            answer_text = merge_activities_intro(
                structured.answer,
                suggest_activities=structured.suggest_activities,
                activities_intro=structured.activities_intro,
            )

            # Extract sources for citation
            sources = self._extract_sources(retrieved_docs) if hasattr(self, 'include_sources') and self.include_sources else []
            
            # Calculate confidence
            confidence = self._calculate_confidence(retrieved_docs)

            # Add sources to response
            if hasattr(self, 'include_sources') and self.include_sources and sources:
                answer_text += "\n\n##### Source documents:"
                for current_source in sources:
                    source_path = current_source['path']
                    source_title = current_source['title']
                    answer_text += f"\n- [{source_title}]({source_path})"
            
            # Add picture paths to response
            if picture_paths:
                answer_text += "\n\n##### Reference images:"
                for picture_path in picture_paths:
                    answer_text += f"\n- [{picture_path.split('/')[-1]}]({picture_path})"
            
            # Format final response
            result = {
                "response": answer_text,
                "sources": sources,
                "confidence": confidence,
                "web_search": structured.web_search,
                "suggest_activities": structured.suggest_activities,
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            return {
                "response": "I apologize, but I encountered an error while generating a response. Please try rephrasing your question.",
                "sources": [],
                "confidence": 0.0,
                "web_search": True,
                "suggest_activities": False,
            }

    def _extract_sources(self, documents: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Extract source information from retrieved documents for citation.
        
        Args:
            documents: List of retrieved document dictionaries
            
        Returns:
            List of source information dictionaries
        """
        sources = []
        seen_sources = set()  # Track unique sources to avoid duplicates
        
        for doc in documents:
            # Extract source and source_path
            source = doc.get("source")
            source_path = doc.get("source_path")
            
            # Skip if no source information is available
            if not source:
                continue
                
            # Create a unique identifier for this source
            source_id = f"{source}|{source_path}"
            
            # Skip if we've already included this source
            if source_id in seen_sources:
                continue
                
            # Add to our sources list
            source_info = {
                "title": source,
                "path": source_path,
                "score": doc.get("combined_score", doc.get("rerank_score", doc.get("score", 0.0)))
            }
            
            sources.append(source_info)
            seen_sources.add(source_id)
        
        # Sort sources by score from highest to lowest
        sources.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        # Format the final sources list, removing the scores which were just used for sorting
        formatted_sources = []
        for source in sources:
            formatted_source = {
                "title": source["title"],
                "path": source["path"]
            }
            formatted_sources.append(formatted_source)
            
        return formatted_sources

    def _calculate_confidence(self, documents: List[Dict[str, Any]]) -> float:
        """
        Calculate confidence score based on retrieved documents.
        
        Args:
            documents: Retrieved documents
            
        Returns:
            Confidence score between 0 and 1
        """
        if not documents:
            return 0.0
            
        # Use combined score (both reranker and cosine similarity) if available, otherwise use original score
        if "combined_score" in documents[0]:
            scores = [doc.get("combined_score", 0) for doc in documents[:3]]
        elif "rerank_score" in documents[0]:
            scores = [doc.get("rerank_score", 0) for doc in documents[:3]]
        else:
            scores = [doc.get("score", 0) for doc in documents[:3]]
            
        # Average of top 3 document scores or fewer if less than 3
        return sum(scores) / len(scores) if scores else 0.0