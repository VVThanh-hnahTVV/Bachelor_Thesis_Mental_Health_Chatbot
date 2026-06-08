# Wellness videos

Helios video activities use `youtube_id` / `video_url` from the API catalog.
The frontend embeds YouTube when `youtube_id` is set; direct MP4/WebM URLs still work.

Update `backend/app/wellness/catalog_seed.py`, then re-seed Mongo:

```bash
cd backend && source .venv/bin/activate
python scripts/seed_wellness_activities.py
```

You may also host files under this directory and set direct URLs like `/videos/wellness/body_scan.mp4`.
