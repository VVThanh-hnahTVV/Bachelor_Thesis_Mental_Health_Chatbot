# Mental health chat platform (greenfield)

Monorepo layout:

- `backend/` — FastAPI, LangGraph, MongoDB, multi-provider LLM (Modal-compatible, Groq, OpenAI, Gemini), lexical RAG over `backend/app/data/knowledge/chunks.json`.
- `frontend/` — Next.js 14 chat + mood dashboard.
- `docker-compose.yml` — local MongoDB.

## Prerequisites

- Python 3.11+
- Node 20+
- Docker (for Mongo)

## Run locally

```bash
docker compose up -d mongo
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # add at least one LLM key
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

Open `http://localhost:3000` (chat) and `http://localhost:3000/dashboard` for mood.

API docs: `http://localhost:8000/docs`.

## Legal / safety

This software is for **educational and wellness support** only. It is **not** medical advice, diagnosis, or emergency care. Configure crisis copy in the backend graph as needed for your jurisdiction.
