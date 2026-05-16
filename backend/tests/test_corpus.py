from app.rag.corpus import lexical_scores


def test_lexical_scores_finds_anxiety_chunk():
    chunks = [
        {"id": "1", "text": "breathing exercises help anxiety", "topic": "anxiety"},
        {"id": "2", "text": "unrelated", "topic": "other"},
    ]
    scored = lexical_scores("I have anxiety and panic", chunks, top_k=2)
    assert scored
    assert "anxiety" in scored[0][1]["text"]
