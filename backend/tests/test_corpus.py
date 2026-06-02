from app.rag.corpus import lexical_scores
from app.rag.embeddings import (
    cosine_similarity,
    embed_documents,
    resolve_embedding_model,
    resolve_embedding_provider,
)
from app.rag.retriever import retrieve_chunks


def test_lexical_scores_finds_anxiety_chunk():
    chunks = [
        {"id": "1", "text": "breathing exercises help anxiety", "topic": "anxiety"},
        {"id": "2", "text": "unrelated", "topic": "other"},
    ]
    scored = lexical_scores("I have anxiety and panic", chunks, top_k=2)
    assert scored
    assert "anxiety" in scored[0][1]["text"]


def test_lexical_scores_handles_vietnamese_tokens():
    chunks = [
        {"id": "1", "text": "bai tap tho giup giam lo au", "topic": "lo au"},
        {"id": "2", "text": "unrelated", "topic": "other"},
    ]
    scored = lexical_scores("toi thay lo au", chunks, top_k=2)
    assert scored
    assert scored[0][1]["id"] == "1"


def test_cosine_similarity():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


async def test_retrieve_chunks_falls_back_to_lexical(monkeypatch):
    class Settings:
        rag_top_k = 2
        rag_min_score = 0.1
        enable_vector_rag = False

    monkeypatch.setattr("app.rag.retriever.get_settings", lambda: Settings())
    chunks, mode = await retrieve_chunks(None, "anxiety panic")
    assert mode in {"lexical", "none"}
    assert isinstance(chunks, list)


def test_resolve_embedding_provider_openai_when_key_set(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)

    class Settings:
        embedding_provider = None
        openai_api_key = "sk-test"
        embedding_model = "nomic-embed-text-v2-moe"
        openai_embedding_model = "text-embedding-3-small"

    monkeypatch.setattr("app.rag.embeddings.get_settings", lambda: Settings())
    assert resolve_embedding_provider() == "openai"
    assert resolve_embedding_model("openai") == "text-embedding-3-small"


def test_resolve_embedding_provider_respects_explicit_ollama(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")

    class Settings:
        embedding_provider = "ollama"
        openai_api_key = "sk-test"

    monkeypatch.setattr("app.rag.embeddings.get_settings", lambda: Settings())
    assert resolve_embedding_provider() == "ollama"


async def test_ollama_embed_documents(monkeypatch):
    calls = []

    class Settings:
        embedding_provider = "ollama"
        embedding_model = "nomic-embed-text-v2-moe"
        ollama_base_url = "http://localhost:11434"

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, json):
            calls.append((url, json))
            return Response()

    monkeypatch.setattr("app.rag.embeddings.get_settings", lambda: Settings())
    monkeypatch.setattr("app.rag.embeddings.httpx.AsyncClient", Client)

    out = await embed_documents(["one", "two"])
    assert out == [[0.1, 0.2], [0.3, 0.4]]
    assert calls[0][0] == "http://localhost:11434/api/embed"
    assert calls[0][1]["model"] == "nomic-embed-text-v2-moe"
