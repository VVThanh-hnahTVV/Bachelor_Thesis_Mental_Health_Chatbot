from app.medical.agents.rag_agent.vectorstore_qdrant import (
    CorpusVectorStore,
    build_qdrant_client,
)
from app.medical.config import get_medical_config


def test_local_qdrant_client_is_shared_per_path():
    cfg = get_medical_config()
    if cfg.rag.url:
        return  # server mode uses separate clients per URL

    path = cfg.rag.vector_local_path
    c1 = build_qdrant_client(vector_local_path=path)
    c2 = build_qdrant_client(vector_local_path=path)
    assert c1 is c2

    pdf = CorpusVectorStore.for_pdf_corpus(cfg)
    web = CorpusVectorStore.for_web_corpus(cfg)
    assert pdf.client is web.client
