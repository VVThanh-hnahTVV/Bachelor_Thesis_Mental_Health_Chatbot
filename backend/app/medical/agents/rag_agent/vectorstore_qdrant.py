import logging
import os
import threading
from uuid import uuid4
from typing import List, Dict, Any, Tuple

from langchain_core.documents import Document
from langchain_classic.storage import LocalFileStore
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams

logger = logging.getLogger(__name__)

# Qdrant local mode allows only one client per storage path per process.
_LOCAL_CLIENT_CACHE: dict[str, QdrantClient] = {}
_LOCAL_CLIENT_LOCK = threading.Lock()


def build_qdrant_client(
    *,
    vector_local_path: str,
    url: str | None = None,
    api_key: str | None = None,
) -> QdrantClient:
    if url:
        return QdrantClient(url=url, api_key=api_key or None)
    with _LOCAL_CLIENT_LOCK:
        cached = _LOCAL_CLIENT_CACHE.get(vector_local_path)
        if cached is not None:
            return cached
        client = QdrantClient(path=vector_local_path)
        _LOCAL_CLIENT_CACHE[vector_local_path] = client
        return client


class CorpusVectorStore:
    """Qdrant hybrid vector store for one corpus (PDF or web)."""

    def __init__(
        self,
        *,
        collection_name: str,
        embedding_dim: int,
        embedding_model,
        top_k: int,
        vector_local_path: str,
        doc_local_path: str,
        url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self.embedding_model = embedding_model
        self.retrieval_top_k = top_k
        self.vectorstore_local_path = vector_local_path
        self.docstore_local_path = doc_local_path
        self.client = build_qdrant_client(
            vector_local_path=vector_local_path,
            url=url,
            api_key=api_key,
        )

    @classmethod
    def for_pdf_corpus(cls, config) -> "CorpusVectorStore":
        return cls(
            collection_name=config.rag.collection_name,
            embedding_dim=config.rag.embedding_dim,
            embedding_model=config.rag.embedding_model,
            top_k=config.rag.top_k,
            vector_local_path=config.rag.vector_local_path,
            doc_local_path=config.rag.doc_local_path,
            url=config.rag.url,
            api_key=config.rag.api_key,
        )

    @classmethod
    def for_web_corpus(cls, config) -> "CorpusVectorStore":
        wc = config.web_corpus
        return cls(
            collection_name=wc.collection_name,
            embedding_dim=config.rag.embedding_dim,
            embedding_model=config.rag.embedding_model,
            top_k=config.rag.top_k,
            vector_local_path=wc.vector_local_path,
            doc_local_path=wc.doc_local_path,
            url=wc.url,
            api_key=wc.api_key,
        )

    def collection_exists(self) -> bool:
        try:
            names = [c.name for c in self.client.get_collections().collections]
            return self.collection_name in names
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Error checking collection: %s", exc)
            return False

    def _create_collection(self) -> None:
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense": VectorParams(size=self.embedding_dim, distance=Distance.COSINE)
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(index=models.SparseIndexParams(on_disk=False))
            },
        )
        self.logger.info("Created collection %s", self.collection_name)

    def _build_vectorstore(self) -> QdrantVectorStore:
        sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
        return QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embedding_model,
            sparse_embedding=sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="dense",
            sparse_vector_name="sparse",
        )

    def try_load_vectorstore(self) -> Tuple[QdrantVectorStore, LocalFileStore] | None:
        if not self.collection_exists():
            return None
        return self.load_vectorstore()

    def load_vectorstore(self) -> Tuple[QdrantVectorStore, LocalFileStore]:
        if not self.collection_exists():
            raise ValueError(f"Collection {self.collection_name} does not exist")
        qdrant_vectorstore = self._build_vectorstore()
        docstore = LocalFileStore(self.docstore_local_path)
        self.logger.info("Loaded vectorstore %s", self.collection_name)
        return qdrant_vectorstore, docstore

    def ingest_chunks(
        self,
        document_chunks: List[str],
        *,
        metadata_base: Dict[str, Any],
    ) -> List[str]:
        doc_ids = [str(uuid4()) for _ in range(len(document_chunks))]
        langchain_documents = []
        for id_idx, chunk in enumerate(document_chunks):
            metadata = {**metadata_base, "doc_id": doc_ids[id_idx]}
            langchain_documents.append(Document(page_content=chunk, metadata=metadata))

        if not self.collection_exists():
            self._create_collection()

        qdrant_vectorstore = self._build_vectorstore()
        docstore = LocalFileStore(self.docstore_local_path)
        qdrant_vectorstore.add_documents(documents=langchain_documents, ids=doc_ids)
        encoded_chunks = [chunk.encode("utf-8") for chunk in document_chunks]
        docstore.mset(list(zip(doc_ids, encoded_chunks)))
        return doc_ids

    def create_vectorstore(
        self,
        document_chunks: List[str],
        document_path: str,
    ) -> Tuple[QdrantVectorStore, LocalFileStore, List[str]]:
        doc_ids = self.ingest_chunks(
            document_chunks,
            metadata_base={
                "source": os.path.basename(document_path),
                "source_path": os.path.join("http://localhost:8000/", document_path),
                "corpus": "medical_pdf",
            },
        )
        qdrant_vectorstore, docstore = self.load_vectorstore()
        return qdrant_vectorstore, docstore, doc_ids

    def retrieve_relevant_chunks(
        self,
        query: str,
        vectorstore: QdrantVectorStore,
        docstore: LocalFileStore,
    ) -> List[Dict[str, Any]]:
        results = vectorstore.similarity_search_with_score(
            query=query,
            k=self.retrieval_top_k,
        )

        retrieved_docs: List[Dict[str, Any]] = []
        for chunk, score in results:
            doc_id = chunk.metadata.get("doc_id")
            if not doc_id:
                continue
            doc_content_bytes = docstore.mget([doc_id])[0]
            if doc_content_bytes is None:
                continue
            doc_content = doc_content_bytes.decode("utf-8")
            retrieved_docs.append(
                {
                    "id": doc_id,
                    "content": doc_content,
                    "score": score,
                    "source": chunk.metadata.get("source", ""),
                    "source_path": chunk.metadata.get("source_path", ""),
                    "corpus": chunk.metadata.get("corpus", ""),
                }
            )
        return retrieved_docs


class VectorStore(CorpusVectorStore):
    """Backward-compatible PDF RAG vector store."""

    def __init__(self, config):
        super().__init__(
            collection_name=config.rag.collection_name,
            embedding_dim=config.rag.embedding_dim,
            embedding_model=config.rag.embedding_model,
            top_k=config.rag.top_k,
            vector_local_path=config.rag.vector_local_path,
            doc_local_path=config.rag.doc_local_path,
            url=config.rag.url,
            api_key=config.rag.api_key,
        )
