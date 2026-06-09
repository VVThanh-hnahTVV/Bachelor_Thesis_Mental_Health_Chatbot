from app.crawl.chunking import chunk_text_by_words


def test_chunk_text_by_words_overlap():
    text = " ".join(f"w{i}" for i in range(600))
    chunks = chunk_text_by_words(text, chunk_size=100, overlap=20)
    assert len(chunks) >= 2
    assert all(len(c.split()) <= 100 for c in chunks)
