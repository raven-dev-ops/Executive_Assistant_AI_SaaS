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
- Redis-backed (shared state): `uvicorn app.main:app --reload --env-file ..\env.dev.redis`


Google Calendar sync (two-way hardening)
---------------------------------------
The backend supports best-effort two-way calendar hardening so owner edits in Google Calendar
are reflected in CRM appointments:

- Create/renew a push notification channel: `POST /v1/calendar/google/watch`
  - Stores channel metadata + the latest `syncToken` on the tenant Business row.
- Receive Google push notifications: `POST /v1/calendar/google/push`
  - Resolves tenant via `X-Goog-Channel-ID` + `X-Goog-Channel-Token` and pulls changes via `syncToken`.
- Legacy/relay webhook shape: `POST /v1/calendar/google/webhook`
  - Accepts an explicit `event_id` + `start/end` fields and updates matching appointments.

Time zones:

- All appointment times are stored as UTC.
- Inbound calendar timestamps are normalized to UTC.
- If an inbound timestamp is *naive* (no timezone offset), it is interpreted in the tenant
  `businesses.time_zone` (IANA name like `America/Chicago` or a fixed offset like `-06:00`),
  falling back to `UTC`.


Multi-instance (shared state)
-----------------------------

If you run more than one backend instance (Kubernetes replicas / multiple pods), use Redis-backed shared state so
sessions and Twilio call routing survive cross-instance requests:

- `SESSION_STORE_BACKEND=redis`
- `TWILIO_STATE_BACKEND=redis`
- `REDIS_URL=redis://...`

Webhook replay/idempotency protection also prefers a shared store when `REDIS_URL` is set:

- `IDEMPOTENCY_STORE_BACKEND=redis` (optional; `REDIS_URL` also auto-enables Redis)
- `IDEMPOTENCY_KEY_PREFIX=idempotency` (optional)


Abuse prevention (rate limiting + lockdown)
-------------------------------------------

Public-facing endpoints are protected by a token-bucket rate limiter in middleware.

**Rate-limited routes**

- `/v1/widget/*` (public chat widget)
- `/v1/chat/*` (chat API)
- `/v1/auth/*` (login/register flows)
- `/v1/public/signup` (when `ALLOW_SELF_SIGNUP=true`)
- `/v1/feedback`
- `/twilio/*` and `/v1/twilio/*` (Twilio webhooks)
- `/telephony/*` and `/v1/telephony/*`
- `/v1/voice/*`

**Configuration**

- `RATE_LIMIT_PER_MINUTE` (default `120`)
- `RATE_LIMIT_BURST` (default `20`)
- `RATE_LIMIT_DISABLED=true` (disable the limiter; not recommended in production)
- `RATE_LIMIT_WHITELIST_IPS=1.2.3.4,5.6.7.8` (comma-separated)

Client IP is derived from `X-Forwarded-For` / `X-Real-IP`, falling back to `request.client.host`.

When limited, endpoints return `429` with a `Retry-After` header.

**Tenant lockdown mode**

When `businesses.lockdown_mode=true`, assistant automation endpoints (widget/chat/voice/telephony/Twilio)
return `423` to pause automation for that tenant while keeping dashboards/admin tools accessible.

Toggle lockdown:

- Owner dashboard: `POST /v1/owner/lockdown` with `{"enabled": true|false}`
- Admin: `PATCH /v1/admin/businesses/{business_id}` with `{"lockdown_mode": true|false}`

**Observability**

- `/metrics` JSON:
  - `rate_limit_blocks_total`
  - `rate_limit_blocks_by_route`
  - `rate_limit_blocks_by_route_business`
- `/metrics/prometheus`:
  - `ai_telephony_rate_limit_blocks_total`


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

