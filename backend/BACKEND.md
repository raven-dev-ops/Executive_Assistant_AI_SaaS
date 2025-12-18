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


Running in Docker
-----------------

To build and run the backend as a container:

```bash
docker build -t ai-telephony-backend ./backend
docker run --rm -p 8000:8000 ai-telephony-backend
```


Observability (Sentry + Uptime Checks)
-------------------------------------

**Error tracking/APM (Sentry)**

Set these environment variables (Sentry is enabled when `SENTRY_DSN` is set):

- `SENTRY_DSN` (required to enable)
- `SENTRY_TRACES_SAMPLE_RATE` (optional, `0` disables APM)
- `SENTRY_ENVIRONMENT` (optional; falls back to `ENVIRONMENT`)
- `SENTRY_RELEASE` (optional; can also use `GIT_SHA`)
- `SENTRY_ENABLED=false` (optional hard-disable)

Captured exceptions include `request_id` and (when available) `business_id` tags.

**Uptime checks (GitHub Actions)**

Configure repo secrets for `.github/workflows/uptime-checks.yml`:

- `UPTIME_BASE_URL` (e.g., `https://your-api.example.com`)
- `UPTIME_BUSINESS_ID` (an active/onboarded tenant for Twilio + widget checks)
- `UPTIME_TWILIO_AUTH_TOKEN` (to sign the synthetic Twilio webhook request)
- `UPTIME_WIDGET_TOKEN` (optional alternative to `X-Business-ID` for the widget check)
- `SLACK_WEBHOOK` (optional notification on workflow failure)

