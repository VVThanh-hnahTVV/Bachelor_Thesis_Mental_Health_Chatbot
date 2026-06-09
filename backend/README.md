# Helios medical chat backend

FastAPI service with multi-agent LangGraph orchestration (Helios), MongoDB persistence, Qdrant RAG, and multi-provider LLM routing.

## API highlights

- `POST /api/v1/chat` — Helios medical assistant (RAG, web search, wellness suggestions)
- `POST /api/v1/chat/stream` — SSE status + final response
- `GET /api/v1/messages?session_id=` — chronological messages
- `POST /api/v1/wellness/start` / `POST /api/v1/wellness/complete` — in-app wellness activities
- `GET /api/v1/activities/catalog` — activity catalog
- `POST /api/v1/activities/rate` — rate completed activities

## Quick start

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,medical]"
cp .env.example .env   # fill keys
docker compose up -d mongo redis
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs`.

## Medical RAG

```bash
pip install -e ".[medical]"
python -m app.medical.ingest --dir data/medical/raw
```

## Wellness activities

```bash
python scripts/seed_wellness_activities.py --ingest-qdrant
```

## Tests

```bash
pytest
```
