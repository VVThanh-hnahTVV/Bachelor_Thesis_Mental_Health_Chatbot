# Luna — Mental Health Chat Platform

Monorepo for an AI companion (**Luna**) that supports emotional wellness and optional medical information lookup. Built as part of a bachelor thesis (IT4995).

## Features

### Psychologist mode (default)

- **LangGraph** conversation workflow with safety engine, crisis escalation, and dynamic quick replies
- **Multi-provider LLM** routing — Groq, OpenAI, Gemini, local Ollama, or a Modal/OpenAI-compatible fine-tuned endpoint, with configurable fallback chain
- **Vector RAG** over curated wellness knowledge (`backend/app/data/knowledge/`) using Ollama embeddings
- **Wellness activities** — inline suggestions (e.g. box breathing, ocean sound) with completion tracking
- **Mood journal** and **PHQ mini screening** on the dashboard
- **User auth** (JWT) with optional session linking
- **Redis** session cache and **MongoDB** persistence

### Medical mode

Toggle in the therapy chat UI. Powered by a multi-agent workflow under `backend/app/medical/` (adapted from [Multi-Agent-Medical-Assistant](https://github.com/souvikmajumder26/Multi-Agent-Medical-Assistant)):

| Agent | Role |
|-------|------|
| Agent decision | Routes queries to the right specialist agent |
| RAG | Qdrant vector search over ingested medical PDFs |
| Web search | Tavily + PubMed / Europe PMC for recent literature |
| CV (optional) | Brain tumor MRI, chest X-ray (COVID), skin lesion image analysis |
| Validation | Human-in-the-loop review for CV outputs before final response |

Medical PDFs ship in `backend/data/medical/raw/`. Run ingest once to populate the local Qdrant store.

## Repository layout

```
├── backend/          FastAPI + LangGraph API
│   ├── app/
│   │   ├── graph/        Psychologist LangGraph workflow
│   │   ├── medical/      Medical multi-agent workflow
│   │   ├── wellness/     Activity planner & recommendations
│   │   ├── rag/          Embeddings & vector retrieval
│   │   └── api/          REST routes
│   └── data/medical/     Raw PDFs + local Qdrant DB
├── frontend/         Next.js 14 (App Router)
│   ├── app/therapy/      Chat session UI (mode toggle)
│   ├── app/dashboard/    Mood, screening, wellness games
│   └── components/         shadcn/ui + therapy components
└── docker-compose.yml    MongoDB + Redis
```

## Prerequisites

- **Python 3.11+**
- **Node.js 20+**
- **Docker** — MongoDB and Redis via Compose
- **[Ollama](https://ollama.com)** — embeddings (`nomic-embed-text-v2-moe`); optional local chat
- **Groq API key** — default chat provider for both modes
- Optional for medical mode: **TAVILY_API_KEY**, **HUGGINGFACE_TOKEN** (reranker), **PUBMED_EMAIL**

## Run locally

### 1. Infrastructure

```bash
docker compose up -d mongo redis
```

### 2. Ollama (embeddings)

```bash
ollama pull nomic-embed-text-v2-moe
```

### 3. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,medical]"
cp .env.example .env   # set GROQ_API_KEY and other keys
```

Ingest medical PDFs into Qdrant (first time, requires `[medical]` extras):

```bash
python -m app.medical.ingest --dir data/medical/raw
```

Start the API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
# optional: create .env.local with NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
npm run dev
```

Open **http://localhost:3000** — start a session at `/therapy/<session-id>` and use the input bar toggle to switch between **Psychologist** and **Medical**.

API docs: **http://localhost:8000/docs**

## Key API endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/chat` | Send a message (`chat_mode`: `psychologist` \| `medical`) |
| `POST /api/v1/chat/upload` | Upload a medical image (medical mode) |
| `POST /api/v1/chat/validate` | Submit human validation for CV results |
| `GET /api/v1/messages?session_id=` | Message history |
| `POST /api/v1/mood` / `GET /api/v1/mood` | Mood journal |
| `POST /api/v1/screening` | PHQ mini screening |
| `POST /api/v1/activities/complete` | Record wellness activity completion |
| `GET /api/v1/dashboard/stats` | Dashboard aggregates |
| `POST /api/auth/register` / `login` | User authentication |

Static CV segmentation images are served at `/uploads/medical/...`.

## Configuration

Copy `backend/.env.example` to `backend/.env`. Important variables:

- **LLM** — `GROQ_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `MODAL_BASE_URL`
- **Embeddings** — `EMBEDDING_PROVIDER=ollama`, `OLLAMA_EMBEDDING_MODEL=nomic-embed-text-v2-moe`
- **Medical** — `ENABLE_MEDICAL_MODE`, `MEDICAL_CV_ENABLED`, `TAVILY_API_KEY`, `HUGGINGFACE_TOKEN`, `PUBMED_EMAIL`
- **Database** — `MONGO_URI` (defaults to local Docker MongoDB)

See [backend/README.md](backend/README.md) for Modal deployment notes and test commands.

## Tests

```bash
cd backend && pytest
```

## Legal / safety

This software is for **educational and wellness support only**. It is **not** medical advice, diagnosis, or emergency care. Medical mode outputs — especially computer-vision analyses — require human validation and must not replace consultation with a licensed healthcare professional. Configure crisis copy in the backend graph as needed for your jurisdiction.
