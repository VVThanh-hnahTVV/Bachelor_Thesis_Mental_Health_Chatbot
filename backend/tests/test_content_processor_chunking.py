from app.medical.agents.rag_agent.content_processor import (
    count_words,
    enforce_word_limits,
    group_sections_into_batches,
    merge_sections_by_split_points,
    parse_llm_split_points,
    split_by_word_window,
    split_header_sections,
)


def test_split_header_sections_restores_heading_marker():
    doc = "Intro paragraph\n# Section A\nContent A\n# Section B\nContent B"
    sections = split_header_sections(doc)
    assert len(sections) == 3
    assert sections[0].startswith("Intro")
    assert sections[1].startswith("# Section A")
    assert sections[2].startswith("# Section B")


def test_group_sections_into_batches_respects_word_budget():
    sections = ["word " * 1000, "word " * 1000, "word " * 1000]
    batches = group_sections_into_batches(
        sections,
        max_words=1500,
        max_sections=10,
    )
    assert len(batches) == 3
    assert batches[0] == [sections[0]]
    assert batches[1] == [sections[1]]
    assert batches[2] == [sections[2]]


def test_group_sections_into_batches_respects_section_limit():
    sections = [f"section {index}" for index in range(10)]
    batches = group_sections_into_batches(
        sections,
        max_words=100_000,
        max_sections=4,
    )
    assert len(batches) == 3
    assert len(batches[0]) == 4
    assert len(batches[1]) == 4
    assert len(batches[2]) == 2


def test_parse_llm_split_points():
    assert parse_llm_split_points("split_after: 1, 3", max_index=5) == [1, 3]
    assert parse_llm_split_points("no splits here", max_index=5) == []
    assert parse_llm_split_points("split_after: 99", max_index=5) == []


def test_merge_sections_by_split_points():
    sections = ["a", "b", "c", "d"]
    merged = merge_sections_by_split_points(sections, [1])
    assert merged == ["a\n\nb", "c\n\nd"]


def test_split_by_word_window_overlap():
    text = " ".join(f"w{i}" for i in range(10))
    chunks = split_by_word_window(text, max_words=4, overlap_words=1)
    assert len(chunks) >= 2
    assert count_words(chunks[0]) == 4


def test_enforce_word_limits_splits_oversized_chunk():
    chunk = " ".join(["term"] * 600)
    parts = enforce_word_limits([chunk], max_words=512, overlap_words=50)
    assert len(parts) >= 2
    assert all(count_words(part) <= 512 for part in parts)
