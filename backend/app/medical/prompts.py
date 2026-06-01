"""Shared LLM formatting instructions for medical chat (rendered as Markdown in UI)."""

MARKDOWN_RESPONSE_INSTRUCTIONS = """
### Output format (required — Markdown for chat UI)
- Write the **entire** reply in Markdown (not plain text only).
- Use markdown bullet lists for causes, tips, or steps, e.g.:
  - Item one
  - Item two
- Put a **blank line** between paragraphs.
- Use **bold** for important labels, especially:
  - **Lưu ý:** for disclaimers (not plain "Lưu ý:" without bold)
  - **Khuyến nghị:** / **Gợi ý:** / **Câu hỏi làm rõ:** when helpful
- You may use `###` for short section headings if needed; keep them small.
- Do **not** wrap the whole answer in a code fence.
- Match the user's language (Vietnamese if they write in Vietnamese).
"""
