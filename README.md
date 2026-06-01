# Mental health chat platform (greenfield)

Monorepo layout:

- `backend/` — FastAPI, LangGraph, MongoDB, multi-provider LLM (Modal-compatible, Groq, OpenAI, Gemini), lexical RAG over `backend/app/data/knowledge/chunks.json`, plus **Medical mode** (`backend/app/medical/`) — vendored multi-agent workflow (Qdrant RAG, web search, optional CV).
- `frontend/` — Next.js 14 chat with **Psychologist / Medical** mode toggle + mood dashboard.
- `docker-compose.yml` — local MongoDB.

## Prerequisites

- Python 3.11+
- Node 20+
- Docker (for Mongo + Redis)
- [Ollama](https://ollama.com) with `nomic-embed-text-v2-moe` for embeddings
- Groq API key (chat for both modes when using default config)

## Run locally

```bash
docker compose up -d mongo redis
ollama pull nomic-embed-text-v2-moe   # once
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,medical]"
cp .env.example .env   # GROQ_API_KEY, TAVILY_API_KEY (optional), HUGGINGFACE_TOKEN (reranker)
# Ingest medical PDFs into Qdrant (first time)
python -m app.medical.ingest --dir data/medical/raw
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

Open `http://localhost:3000/therapy/<session-id>` — use the input bar toggle **Psychologist** vs **Medical**.

API docs: `http://localhost:8000/docs` (`POST /api/v1/chat` with `chat_mode`, `/api/v1/chat/upload`, `/api/v1/chat/validate`).

## Legal / safety

This software is for **educational and wellness support** only. It is **not** medical advice, diagnosis, or emergency care. Configure crisis copy in the backend graph as needed for your jurisdiction.
