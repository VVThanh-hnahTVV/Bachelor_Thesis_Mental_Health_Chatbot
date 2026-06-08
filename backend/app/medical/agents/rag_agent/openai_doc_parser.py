"""Parse PDFs via OpenAI file input (no local Docling / CPU VLM)."""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, List, Tuple

from langchain_core.messages import HumanMessage
from pypdf import PdfReader, PdfWriter

from app.medical.agents.rag_agent.doc_parser import MarkdownParsedDocument
from app.medical.llm import build_ingest_llm

_EXTRACT_PROMPT = """Extract all text from this PDF section as clean markdown for a medical RAG knowledge base.

Rules:
- Preserve headings (# ## ###), lists, and tables (markdown table syntax).
- Include figure/table captions when present.
- Transcribe faithfully; do not summarize or add commentary.
- This batch covers pages {start_page}–{end_page} of the source document.
- Output markdown only, no preamble.
"""


class OpenAIDocParser:
    """Extract PDF text through OpenAI vision/file API in page batches."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.logger.info("OpenAI document parser initialized (cloud PDF extraction)")

    def parse_document(
        self,
        document_path: str,
        output_dir: str,
        **_kwargs: Any,
    ) -> Tuple[MarkdownParsedDocument, List[str]]:
        path = Path(document_path)
        if not path.is_file():
            raise FileNotFoundError(f"Document not found: {document_path}")

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        reader = PdfReader(str(path))
        total_pages = len(reader.pages)
        batch_size = max(1, int(os.getenv("INGEST_PARSE_PAGES_PER_BATCH", "8")))
        llm = build_ingest_llm(temperature=0.0, for_vision=True)

        sections: list[str] = []
        for start in range(0, total_pages, batch_size):
            end = min(start + batch_size, total_pages)
            start_page = start + 1
            end_page = end
            self.logger.info(
                "OpenAI parse: pages %s–%s / %s",
                start_page,
                end_page,
                total_pages,
            )

            pdf_bytes = self._extract_page_range_bytes(reader, start, end)
            pdf_data_url = (
                "data:application/pdf;base64,"
                + base64.b64encode(pdf_bytes).decode("utf-8")
            )
            prompt = _EXTRACT_PROMPT.format(start_page=start_page, end_page=end_page)
            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "file",
                        "file": {
                            "filename": f"{path.stem}_p{start_page}-{end_page}.pdf",
                            "file_data": pdf_data_url,
                        },
                    },
                ]
            )
            response = llm.invoke([message])
            text = response.content if isinstance(response.content, str) else str(response.content)
            sections.append(text.strip())

        markdown = "\n\n---\n\n".join(section for section in sections if section)
        self.logger.info(
            "OpenAI parse complete: %s pages -> %s characters",
            total_pages,
            len(markdown),
        )
        return MarkdownParsedDocument(markdown=markdown), []

    @staticmethod
    def _extract_page_range_bytes(reader: PdfReader, start: int, end: int) -> bytes:
        writer = PdfWriter()
        for page_index in range(start, end):
            writer.add_page(reader.pages[page_index])
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()
