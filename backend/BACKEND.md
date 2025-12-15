Backend Service
===============

This directory contains the Python backend for the AI telephony assistant and CRM. It implements
the Phase 1 design described in `PHASE1_VOICE_ASSISTANT_DESIGN.md` (voice assistant + scheduling).

Status: **partial implementation** ƒ?" endpoints and services are stubbed for STT/TTS and Google
Calendar, but Twilio webhooks for inbound voice and SMS are wired to the backend.


Quick start (development)
-------------------------

From the repository root:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # On Windows
pip install -e .[dev]
uvicorn app.main:app --reload
```

Then visit `http://localhost:8000/docs` for the interactive API docs.

For profile-based setups (stub vs DB-backed), see the env files in the repo root:

- In-memory: `uvicorn app.main:app --reload --env-file ..\env.dev.inmemory`
- DB-backed (SQLite): `uvicorn app.main:app --reload --env-file ..\env.dev.db`

Shared state and multi-instance setup
-------------------------------------
- Call/session state: `app.services.sessions` supports Redis when `SESSION_STORE_BACKEND=redis` (and `REDIS_URL`), which is also the default in `docker-compose.yml`. Use this in any multi-replica deployment to keep call/chat sessions coherent across instances.
- Twilio call/SMS state + pending actions: set `TWILIO_STATE_BACKEND=redis` (with `REDIS_URL`) so call_sid → session_id links, SMS conversation routing, and pending cancel/reschedule actions survive across workers.
- Rate limit buckets: the in-app `RateLimiter` is per-process; for production/global enforcement, pair it with an edge limiter (Cloudflare/WAF/API Gateway) using the same per-IP/per-tenant thresholds.
- OAuth/token stubs: the stub `InMemoryOAuthStore` is process-local. For real provider tokens, back it with your DB/secret store so refresh tokens are shared across instances.
- Replay/idempotency caches: Twilio replay/drop windows and Stripe replay protection use short-lived in-memory maps; run behind sticky load balancing or move those keys into Redis if you need cross-replica dedupe.
- Tests: `backend/tests/test_session_store_backends.py` includes a cross-instance Redis test to validate shared sessions.

Webhook security and dedupe knobs
---------------------------------

Twilio/Stripe webhook hardening can be tuned via env vars:

- `VERIFY_TWILIO_SIGNATURES=true` and `TWILIO_AUTH_TOKEN` are required in prod for Twilio webhooks.
- `REPLAY_PROTECTION_SECONDS` (Twilio) and `STRIPE_REPLAY_PROTECTION_SECONDS` (Stripe) bound replay windows.
- `STREAM_DEDUPE_TTL_SECONDS` (default 600) controls how long Twilio stream IDs are remembered for duplicate drop across workers.
- `SMS_EVENT_DEDUPE_TTL_SECONDS` (default 300) controls how long SMS EventIds are remembered per tenant/phone for idempotency.
- `LOG_FORMAT=json` (default in prod), `LOG_SERVICE_NAME=ai-telephony-backend`, and `LOG_LEVEL` tune structured logging for shipping to a central sink.

SQLite backup/restore (dev/stub)
--------------------------------

- Backup: `python scripts/backup_db.py --db ./app.db --out ./backups`
- Restore: `python scripts/backup_db.py restore --db ./app.db --backup ./backups/app-<timestamp>.db`
- DR drill: restore into a clean env, run smoke flows (voice/chat, webhook hits, dashboard), and record RPO/RTO timestamps.


Running in Docker
-----------------

To build and run the backend as a container:

```bash
docker build -t ai-telephony-backend ./backend
docker run --rm -p 8000:8000 ai-telephony-backend
```
