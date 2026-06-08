import json
from pathlib import Path

from app.medical.rag_catalog import (
    build_decision_system_prompt,
    build_rag_catalog_section,
    list_raw_documents,
)


def test_catalog_lists_pdfs_from_raw_dir(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "brain_tumor_2024.pdf").write_bytes(b"%PDF")
    (raw_dir / "notes.txt").write_text("ignore me", encoding="utf-8")

    metadata_path = tmp_path / "document_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "documents": {
                    "brain_tumor_2024.pdf": {
                        "title": "Brain tumor paper",
                        "topics": ["brain_tumor"],
                        "document_type": "research_paper",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    entries = list_raw_documents(str(raw_dir), str(metadata_path))

    assert len(entries) == 1
    assert entries[0].filename == "brain_tumor_2024.pdf"
    assert entries[0].title == "Brain tumor paper"
    assert "brain_tumor" in entries[0].topics


def test_catalog_falls_back_when_metadata_missing(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "covid_chest_xray_2024.pdf").write_bytes(b"%PDF")

    entries = list_raw_documents(str(raw_dir), str(tmp_path / "missing.json"))

    assert entries[0].title == "Covid Chest Xray 2024"
    assert "chest_imaging" in entries[0].topics


def test_decision_prompt_includes_raw_catalog(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "skin_lesion_2023.pdf").write_bytes(b"%PDF")

    prompt = build_decision_system_prompt(str(raw_dir), str(tmp_path / "missing.json"))

    assert "skin_lesion_2023.pdf" in prompt
    assert "RAG_AGENT" in prompt
    assert "skin_lesion" in prompt
