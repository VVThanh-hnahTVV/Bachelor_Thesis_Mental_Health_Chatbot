# Helios — Tra cứu & tư vấn sức khỏe tâm thần

Monorepo cho **Helios** — nền tảng hỗ trợ tra cứu và tư vấn sức khỏe tâm thần với AI đa agent, RAG, web search và bài tập thư giãn. Luận văn IT4995.

## Features

- **Multi-agent LangGraph** — conversation, RAG (Qdrant), Tavily/PubMed web search, guardrails
- **Multi-provider LLM** — Groq, OpenAI, Gemini, local Ollama, or Modal fine-tuned endpoint
- **Wellness activities** — semantic suggestions after answers; in-app breathing/audio exercises with ratings
- **User auth** (JWT) with optional session linking
- **Redis** session cache and **MongoDB** persistence
- **Speech-to-text** via ElevenLabs (optional)

## Repository layout

```
├── backend/          FastAPI + LangGraph API
│   ├── app/medical/      Helios multi-agent workflow
│   ├── app/wellness/     Activity catalog & session helpers
│   └── data/medical/     Raw PDFs + Qdrant index
├── frontend/         Next.js (App Router)
│   ├── app/therapy/      Helios chat UI
│   └── app/dashboard/    Wellness dashboard
└── docker-compose.yml    MongoDB + Redis
```

## Quick start

```bash
# Infrastructure
docker compose up -d mongo redis

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,medical]"
cp .env.example .env   # fill API keys
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

## API

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/chat` | Send a message to Helios |
| `POST /api/v1/chat/stream` | SSE status + response |
| `GET /api/v1/messages` | Chat history |
| `GET /api/v1/activities/catalog` | Wellness activity catalog |

See [backend/README.md](backend/README.md) for ingest scripts and env vars.
