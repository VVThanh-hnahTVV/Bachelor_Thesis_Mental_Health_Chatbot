# Mental health chat backend

FastAPI service with LangGraph orchestration, MongoDB persistence, and multi-provider LLM routing (Modal OpenAI-compatible, Groq, OpenAI, Gemini).

## API highlights

- `POST /api/v1/chat` — returns `assistant_message_id` and LLM-detected `suggested_activities` (when risk is not high) for inline wellness UI.
- `GET /api/v1/messages?session_id=` — chronological messages with ids.
- `POST /api/v1/activities/complete` — body: `session_id`, `activity_id` (`breathing_box` | `ocean_sound`), optional `linked_message_id`, optional `duration_sec`.
- `GET /api/v1/activities?session_id=` — list completions for badges in the UI.

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill keys
# from repo root:
docker compose up -d mongo
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs`.

## Modal (fine-tuned) endpoint

Deploy your model behind an **OpenAI-compatible** HTTP API (for example vLLM, TGI, or LiteLLM on [Modal](https://modal.com)). Set:

- `MODAL_BASE_URL` — base URL including `/v1` if your proxy expects it (LangChain `ChatOpenAI` appends `/chat/completions` to the base host; use the host root your stack documents).
- `MODAL_API_KEY` — token your gateway expects (use `dummy` if none).
- `MODAL_MODEL` — model id string your server expects.

Cold starts on serverless GPU can timeout; configure `LLM_FALLBACK_CHAIN` (e.g. `groq,openai,gemini`) so `invoke_with_fallback` can continue if Modal is slow or down.

## Environment

See [.env.example](.env.example).

## Tests

```bash
pytest
```

## Lexical RAG

Curated snippets live in `app/data/knowledge/chunks.json`. Runtime retrieval is keyword overlap (no embedding dependency). Extend `scripts/seed_vectorstore.py` if you add Chroma/OpenAI embeddings later.
