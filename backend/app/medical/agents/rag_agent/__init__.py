import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any, Tuple

from .doc_parser import create_doc_parser
from .content_processor import ContentProcessor
from .vectorstore_qdrant import CorpusVectorStore, VectorStore
from .reranker import Reranker
from .query_expander import (
    cap_chunks,
    dedupe_chunks,
    dedupe_picture_paths,
    normalize_sub_queries,
)
from .response_generator import ResponseGenerator

_rag_singleton: "MedicalRAG | None" = None


def get_medical_rag(config) -> "MedicalRAG":
    """Reuse one MedicalRAG per process (heavy models + single Qdrant local client)."""
    global _rag_singleton
    if _rag_singleton is None:
        _rag_singleton = MedicalRAG(config)
    return _rag_singleton


class MedicalRAG:
    """
    Medical Retrieval-Augmented Generation system that integrates all components.
    """
    def __init__(self, config):
        """
        Initialize the RAG Agent.
        
        Args:
            config: Configuration object with RAG settings
        """
        # Set up logging
        self.logger = logging.getLogger(f"{self.__module__}")
        self.logger.info("Initializing Medical RAG system")
        self.config = config
        self.doc_parser = create_doc_parser()
        self.content_processor = ContentProcessor(config)
        self.vector_store = VectorStore(config)
        self.web_vector_store = CorpusVectorStore.for_web_corpus(config)
        self.reranker = Reranker(config)
        self.response_generator = ResponseGenerator(config)
        self.parsed_content_dir = self.config.rag.parsed_content_dir
        self._rerank_lock = threading.Lock()
    
    def ingest_directory(self, directory_path: str) -> Dict[str, Any]:
        """
        Ingest all files in a directory into the RAG system.
        
        Args:
            directory_path: Path to the directory containing files to ingest
            
        Returns:
            Dictionary with ingestion results
        """
        start_time = time.time()
        self.logger.info(f"Ingesting files from directory: {directory_path}")
        
        try:
            # Check if directory exists
            if not os.path.isdir(directory_path):
                raise ValueError(f"Directory not found: {directory_path}")
            
            # Get all files in the directory
            files = [os.path.join(directory_path + '/', f) for f in os.listdir(directory_path) 
                     if os.path.isfile(os.path.join(directory_path, f))]
            
            if not files:
                self.logger.warning(f"No files found in directory: {directory_path}")
                return {
                    "success": True,
                    "documents_ingested": 0,
                    "chunks_processed": 0,
                    "processing_time": time.time() - start_time
                }
            
            # Track statistics
            total_chunks_processed = 0
            successful_ingestions = 0
            failed_ingestions = 0
            failed_files = []
            
            # Process each file
            for file_path in files:
                self.logger.info(f"Processing file {successful_ingestions + failed_ingestions + 1}/{len(files)}: {file_path}")
                
                try:
                    result = self.ingest_file(file_path)
                    if result["success"]:
                        successful_ingestions += 1
                        total_chunks_processed += result.get("chunks_processed", 0)
                    else:
                        failed_ingestions += 1
                        failed_files.append({"file": file_path, "error": result.get("error", "Unknown error")})
                except Exception as e:
                    self.logger.error(f"Error processing file {file_path}: {e}")
                    failed_ingestions += 1
                    failed_files.append({"file": file_path, "error": str(e)})
            
            return {
                "success": True,
                "documents_ingested": successful_ingestions,
                "failed_documents": failed_ingestions,
                "failed_files": failed_files,
                "chunks_processed": total_chunks_processed,
                "processing_time": time.time() - start_time
            }
            
        except Exception as e:
            self.logger.error(f"Error ingesting directory: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time
            }
    
    def ingest_file(self, document_path: str) -> Dict[str, Any]:
        """
        Ingest a single file into the RAG system.
        
        Args:
            document_path: Path to the file to ingest
            
        Returns:
            Dictionary with ingestion results
        """
        start_time = time.time()
        self.logger.info(f"Ingesting file: {document_path}")

        try:
            # Step 1: Parse document
            self.logger.info("1. Parsing document and extracting images...")
            parsed_document, images = self.doc_parser.parse_document(document_path, self.parsed_content_dir)
            self.logger.info(f"   Parsed document and extracted {len(images)} images")

            # Step 2: Summarize images
            self.logger.info("2. Summarizing images...")
            image_summaries = self.content_processor.summarize_images(images)
            self.logger.info(f"   Generated {len(image_summaries)} image summaries")

            # Step 3: Format document with image summaries
            self.logger.info("3. Formatting document with image summaries...")
            formatted_document = self.content_processor.format_document_with_images(parsed_document, image_summaries)

            # Step 4: Chunk document into semantic sections
            self.logger.info("4. Chunking document into semantic sections...")
            document_chunks = self.content_processor.chunk_document(formatted_document)
            self.logger.info(f"   Document split into {len(document_chunks)} chunks")

            # Step 5: Create vector store and document store
            self.logger.info("5. Creating vector store knowledge base...")
            self.vector_store.create_vectorstore(
                document_chunks=document_chunks, 
                document_path=document_path
                )
            
            return {
                "success": True,
                "documents_ingested": 1,
                "chunks_processed": len(document_chunks),
                "processing_time": time.time() - start_time
            }
        
        except Exception as e:
            self.logger.error(f"Error ingesting file: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time
            }
        
    def _retrieve_for_subquery(self, sub_query: str) -> List[Dict[str, Any]]:
        """Retrieve relevant chunks from PDF and web corpora for one sub-query."""
        retrieved_documents: List[Dict[str, Any]] = []

        try:
            pdf_loaded = self.vector_store.try_load_vectorstore()
            if pdf_loaded is not None:
                pdf_vs, pdf_ds = pdf_loaded
                retrieved_documents.extend(
                    self.vector_store.retrieve_relevant_chunks(
                        query=sub_query,
                        vectorstore=pdf_vs,
                        docstore=pdf_ds,
                    )
                )
        except Exception as pdf_exc:  # noqa: BLE001
            self.logger.warning("PDF corpus retrieval skipped: %s", pdf_exc)

        try:
            web_loaded = self.web_vector_store.try_load_vectorstore()
            if web_loaded is not None:
                web_vs, web_ds = web_loaded
                retrieved_documents.extend(
                    self.web_vector_store.retrieve_relevant_chunks(
                        query=sub_query,
                        vectorstore=web_vs,
                        docstore=web_ds,
                    )
                )
        except Exception as web_exc:  # noqa: BLE001
            self.logger.warning("Web corpus retrieval skipped: %s", web_exc)

        retrieved_documents.sort(key=lambda doc: doc.get("score", 0.0))
        top_k = self.config.rag.top_k
        return retrieved_documents[: top_k * 2]

    def _retrieve_and_rerank_subquery(
        self,
        sub_query: str,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Retrieve and rerank chunks for a single sub-query."""
        retrieved_documents = self._retrieve_for_subquery(sub_query)
        self.logger.info(
            "   Sub-query '%s': retrieved %d chunks",
            sub_query,
            len(retrieved_documents),
        )

        if self.reranker and len(retrieved_documents) > 1:
            with self._rerank_lock:
                reranked_documents, picture_paths = self.reranker.rerank(
                    sub_query,
                    retrieved_documents,
                    self.parsed_content_dir,
                )
            self.logger.info(
                "   Sub-query '%s': reranked to %d chunks",
                sub_query,
                len(reranked_documents),
            )
            return reranked_documents, picture_paths

        return retrieved_documents, []

    def process_query(
        self,
        query: str,
        chat_history: Optional[str] = None,
        sub_queries: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Process a query with the RAG system.
        
        Args:
            query: The original user query string
            chat_history: Optional chat history for context
            sub_queries: Optional retrieval sub-queries from the route agent
            
        Returns:
            Response dictionary
        """
        start_time = time.time()
        original_query = query
        normalized_sub_queries = normalize_sub_queries(
            sub_queries,
            original_query,
            max_count=self.config.rag.max_sub_queries,
        )
        self.logger.info("RAG Agent processing query: %s", original_query)
        self.logger.info("RAG sub-queries: %s", normalized_sub_queries)
        
        try:
            all_documents: List[Dict[str, Any]] = []
            all_picture_paths: List[str] = []

            max_workers = min(len(normalized_sub_queries), self.config.rag.max_sub_queries)
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(self._retrieve_and_rerank_subquery, sub_query): sub_query
                    for sub_query in normalized_sub_queries
                }
                for future in as_completed(futures):
                    sub_query = futures[future]
                    try:
                        reranked_docs, picture_paths = future.result()
                        all_documents.extend(reranked_docs)
                        all_picture_paths.extend(picture_paths)
                    except Exception as sub_exc:  # noqa: BLE001
                        self.logger.warning(
                            "Sub-query '%s' failed: %s",
                            sub_query,
                            sub_exc,
                        )

            self.logger.info(
                "   Merged %d chunks before dedupe",
                len(all_documents),
            )
            merged_documents = cap_chunks(
                dedupe_chunks(all_documents),
                self.config.rag.context_limit,
            )
            merged_picture_paths = dedupe_picture_paths(all_picture_paths)
            self.logger.info(
                "   %d chunks after dedupe and cap",
                len(merged_documents),
            )

            self.logger.info("Generating response...")
            response = self.response_generator.generate_response(
                query=original_query,
                retrieved_docs=merged_documents,
                picture_paths=merged_picture_paths,
                chat_history=chat_history,
            )
            
            processing_time = time.time() - start_time
            response["processing_time"] = processing_time
            
            return response
        
        except Exception as e:
            self.logger.error(f"Error processing query: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {
                "response": f"I encountered an error while processing your query: {str(e)}",
                "sources": [],
                "confidence": 0.0,
                "web_search": True,
                "suggest_activities": False,
                "processing_time": time.time() - start_time
            }