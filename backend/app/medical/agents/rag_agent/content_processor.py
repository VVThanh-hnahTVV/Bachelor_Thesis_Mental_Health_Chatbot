import base64
import logging
import re
from mimetypes import guess_type
from pathlib import Path
from typing import Any, List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

_HEADER_SPLIT = "\n#"
_CHUNK_MARKER_PATTERN = re.compile(
    r"<\|start_chunk_(\d+)\|>(.*?)<\|end_chunk_\1\|>",
    re.DOTALL,
)

_CHUNKING_PROMPT = """
You are an assistant specialized in splitting text into semantically consistent sections.

Following is the document text:
<document>
{document_text}
</document>

<instructions>
Instructions:
    1. The text has been divided into chunks, each marked with <|start_chunk_X|> and <|end_chunk_X|> tags, where X is the chunk number.
    2. Identify points where splits should occur, such that consecutive chunks of similar themes stay together.
    3. Each output section should be roughly {min_words} to {max_words} words when merged.
    4. If chunks 1 and 2 belong together but chunk 3 starts a new topic, suggest a split after chunk 2.
    5. The chunks must be listed in ascending order.
    6. Provide your response in the form: 'split_after: 3, 5'.
</instructions>

Respond only with the IDs of the chunks where you believe a split should occur.
YOU MUST RESPOND WITH AT LEAST ONE SPLIT.
""".strip()


def _image_ref_to_data_url(image_ref: str) -> str:
    """Convert a local path or file URI into a base64 data URL for remote vision APIs."""
    if image_ref.startswith(("data:", "http://", "https://")):
        return image_ref

    path = Path(image_ref.removeprefix("file://"))
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {image_ref}")

    mime_type, _ = guess_type(path)
    if mime_type is None:
        mime_type = "image/png"

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def count_words(text: str) -> int:
    return len(text.split())


def split_header_sections(formatted_document: str) -> list[str]:
    """Pre-split markdown on heading boundaries."""
    parts = formatted_document.split(_HEADER_SPLIT)
    sections: list[str] = []
    for index, part in enumerate(parts):
        text = part.strip()
        if not text:
            continue
        if index > 0:
            text = text.lstrip("#").lstrip()
            text = f"# {text}"
        sections.append(text)
    return sections


def group_sections_into_batches(
    sections: list[str],
    *,
    max_words: int,
    max_sections: int,
) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    current_words = 0

    for section in sections:
        section_words = count_words(section)
        overflow = current and (
            current_words + section_words > max_words
            or len(current) >= max_sections
        )
        if overflow:
            batches.append(current)
            current = [section]
            current_words = section_words
        else:
            current.append(section)
            current_words += section_words

    if current:
        batches.append(current)
    return batches


def wrap_sections_with_markers(sections: list[str]) -> str:
    lines: list[str] = []
    for index, section in enumerate(sections):
        lines.append(f"<|start_chunk_{index}|>\n{section}\n<|end_chunk_{index}|>")
    return "\n".join(lines) + "\n"


def split_by_word_window(
    text: str,
    *,
    max_words: int,
    overlap_words: int,
) -> list[str]:
    """Fixed-size word windows — reliable fallback for oversized sections."""
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [text.strip()]

    overlap = max(0, min(overlap_words, max_words // 2))
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = max(start + 1, end - overlap)
    return chunks


def merge_sections_by_split_points(
    sections: list[str],
    split_after: list[int],
) -> list[str]:
    if not sections:
        return []
    if not split_after:
        merged = "\n\n".join(sections).strip()
        return [merged] if merged else []

    outputs: list[str] = []
    current: list[str] = []
    for index, section in enumerate(sections):
        current.append(section)
        if index in split_after:
            merged = "\n\n".join(current).strip()
            if merged:
                outputs.append(merged)
            current = []

    if current:
        merged = "\n\n".join(current).strip()
        if merged:
            outputs.append(merged)
    return outputs


def parse_llm_split_points(llm_response: str, *, max_index: int) -> list[int]:
    if "split_after:" not in llm_response:
        return []
    split_points = llm_response.split("split_after:", 1)[1].strip()
    parsed: list[int] = []
    for token in split_points.replace(",", " ").split():
        if not token.strip().isdigit():
            continue
        index = int(token.strip())
        if 0 <= index <= max_index:
            parsed.append(index)
    return sorted(set(parsed))


def enforce_word_limits(
    chunks: list[str],
    *,
    max_words: int,
    overlap_words: int,
) -> list[str]:
    normalized: list[str] = []
    for chunk in chunks:
        normalized.extend(
            split_by_word_window(
                chunk,
                max_words=max_words,
                overlap_words=overlap_words,
            )
        )
    return normalized


class ContentProcessor:
    """
    Processes parsed content — summarizes images, creates semantic chunks.

    Chunking strategy (hybrid):
      1. Pre-split on markdown headings (fast, scales to any PDF size).
      2. Batch LLM merge suggestions within token-safe windows.
      3. Fixed word-window fallback when LLM is disabled or fails.
    """

    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        rag = config.rag
        self.summarizer_model = rag.summarizer_model
        self.chunker_model = rag.chunker_model
        self.chunk_max_words = rag.chunk_size
        self.chunk_overlap_words = rag.chunk_overlap
        self.chunk_batch_max_words = rag.chunk_batch_max_words
        self.chunk_batch_max_sections = rag.chunk_batch_max_sections
        self.enable_llm_chunking = rag.enable_llm_chunking
        self.chunk_target_min_words = rag.chunk_target_min_words

    def summarize_images(self, images: List[str]) -> List[str]:
        prompt_template = """Describe the image in detail while keeping it concise and to the point.
                        For context, the image is part of either a medical research paper or a research paper
                        demonstrating the use of artificial intelligence techniques like
                        machine learning and deep learning in diagnosing diseases or a medical report.
                        Be specific about graphs, such as bar plots if they are present in the image.
                        Only summarize what is present in the image, without adding any extra detail or comment.
                        Summarize the image only if it is related to the context, return 'non-informative' explicitly
                        if the image is of some button not relevant to the context."""

        messages = [
            (
                "user",
                [
                    {"type": "text", "text": prompt_template},
                    {
                        "type": "image_url",
                        "image_url": {"url": "{image}"},
                    },
                ],
            )
        ]

        prompt = ChatPromptTemplate.from_messages(messages)
        summary_chain = prompt | self.summarizer_model | StrOutputParser()

        results = []
        for image in images:
            try:
                image_url = _image_ref_to_data_url(image)
                summary = summary_chain.invoke({"image": image_url})
                results.append(summary)
            except Exception as exc:
                self.logger.warning("Error processing image %s: %s", image, exc)
                results.append("no image summary")

        return results

    def format_document_with_images(self, parsed_document: Any, image_summaries: List[str]) -> str:
        image_placeholder = "<!-- image_placeholder -->"
        page_break_placeholder = "<!-- page_break -->"

        formatted_parsed_document = parsed_document.export_to_markdown(
            page_break_placeholder=page_break_placeholder,
            image_placeholder=image_placeholder,
        )

        return self._replace_occurrences(
            formatted_parsed_document,
            image_placeholder,
            image_summaries,
        )

    def _replace_occurrences(self, text: str, target: str, replacements: List[str]) -> str:
        result = text
        for counter, replacement in enumerate(replacements):
            if target in result:
                if replacement.lower() != "non-informative":
                    result = result.replace(
                        target,
                        f"picture_counter_{counter} {replacement}",
                        1,
                    )
                else:
                    result = result.replace(target, "", 1)
            else:
                break
        return result

    def chunk_document(self, formatted_document: str) -> List[str]:
        sections = split_header_sections(formatted_document)
        if not sections:
            return []

        batches = group_sections_into_batches(
            sections,
            max_words=self.chunk_batch_max_words,
            max_sections=self.chunk_batch_max_sections,
        )
        self.logger.info(
            "Chunking %d header sections in %d batch(es) "
            "(llm=%s, max_words=%d, max_sections=%d)",
            len(sections),
            len(batches),
            self.enable_llm_chunking,
            self.chunk_batch_max_words,
            self.chunk_batch_max_sections,
        )

        outputs: list[str] = []
        for batch_index, batch in enumerate(batches, start=1):
            batch_chunks = self._chunk_section_batch(batch, batch_index, len(batches))
            outputs.extend(batch_chunks)

        return enforce_word_limits(
            outputs,
            max_words=self.chunk_max_words,
            overlap_words=self.chunk_overlap_words,
        )

    def _chunk_section_batch(
        self,
        sections: list[str],
        batch_index: int,
        batch_count: int,
    ) -> list[str]:
        batch_words = sum(count_words(section) for section in sections)
        use_llm = (
            self.enable_llm_chunking
            and len(sections) > 1
            and batch_words >= self.chunk_target_min_words
        )
        if not use_llm:
            merged = "\n\n".join(sections).strip()
            return [merged] if merged else []

        marked = wrap_sections_with_markers(sections)
        prompt = _CHUNKING_PROMPT.format(
            document_text=marked,
            min_words=self.chunk_target_min_words,
            max_words=self.chunk_max_words,
        )
        try:
            response = self.chunker_model.invoke(prompt)
            llm_text = response.content if hasattr(response, "content") else str(response)
            split_after = parse_llm_split_points(
                str(llm_text),
                max_index=len(sections) - 1,
            )
            if not split_after:
                self.logger.warning(
                    "Batch %d/%d: LLM returned no split points; using pre-split sections",
                    batch_index,
                    batch_count,
                )
                return merge_sections_by_split_points(sections, [])
            merged = merge_sections_by_split_points(sections, split_after)
            self.logger.info(
                "Batch %d/%d: LLM produced %d chunk(s) from %d section(s)",
                batch_index,
                batch_count,
                len(merged),
                len(sections),
            )
            return merged
        except Exception as exc:
            self.logger.warning(
                "Batch %d/%d: LLM chunking failed (%s); using fixed word split",
                batch_index,
                batch_count,
                exc,
            )
            merged = "\n\n".join(sections).strip()
            return split_by_word_window(
                merged,
                max_words=self.chunk_max_words,
                overlap_words=self.chunk_overlap_words,
            )

    def _split_text_by_llm_suggestions(self, chunked_text: str, llm_response: str) -> List[str]:
        """Legacy helper — kept for compatibility with marker-based responses."""
        matches = _CHUNK_MARKER_PATTERN.findall(chunked_text)
        if not matches:
            text = chunked_text.strip()
            return [text] if text else []

        sections = [text for _, text in matches]
        split_after = parse_llm_split_points(llm_response, max_index=len(sections) - 1)
        return merge_sections_by_split_points(sections, split_after)
