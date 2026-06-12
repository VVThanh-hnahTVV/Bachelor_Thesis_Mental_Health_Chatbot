from app.medical.agents.rag_agent.vectorstore_qdrant import CorpusVectorStore


def test_extract_doc_id_from_nested_metadata():
    payload = {"metadata": {"doc_id": "abc-123", "source_id": "web-1"}}
    assert CorpusVectorStore._extract_doc_id(payload) == "abc-123"


def test_extract_doc_id_from_root_payload():
    payload = {"doc_id": "root-id"}
    assert CorpusVectorStore._extract_doc_id(payload) == "root-id"


def test_extract_doc_id_missing():
    assert CorpusVectorStore._extract_doc_id({}) is None
    assert CorpusVectorStore._extract_doc_id(None) is None
