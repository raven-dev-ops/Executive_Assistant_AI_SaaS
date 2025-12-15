AI Telephony Service & CRM for Trades
=====================================

![Backend CI](https://github.com/raven-dev-ops/ai_telephony_service_crm/actions/workflows/backend-ci.yml/badge.svg)
![Perf Smoke](https://github.com/raven-dev-ops/ai_telephony_service_crm/actions/workflows/perf-smoke.yml/badge.svg)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A585%25-brightgreen)](https://github.com/raven-dev-ops/ai_telephony_service_crm/actions/workflows/backend-ci.yml)

AI-powered telephony and lightweight CRM for small trades businesses (reference tenant: Bristol Plumbing, Merriam KS). The assistant acts as a 24/7 virtual receptionist that answers calls/chats, triages emergencies, schedules on Google Calendar, and keeps a searchable history of customers and jobs.

Quick Start (local dev)
-----------------------
1) Backend  
   ```bash
   cd backend
   python -m venv .venv && .venv\Scripts\activate  # Windows
   # or: source .venv/bin/activate                # Unix
   pip install -e .[dev]
   uvicorn app.main:app --reload                  # uses defaults
   # or use provided envs:
   #   uvicorn app.main:app --reload --env-file ..\env.dev.inmemory
   #   uvicorn app.main:app --reload --env-file ..\env.dev.db
   # With docker-compose (includes Redis for shared session store):
   #   docker-compose up --build
   ```

2) Owner dashboard  
   - Open `dashboard/index.html` (file:// or `python -m http.server` from repo root).  
   - Set `X-API-Key` and `X-Owner-Token` from your tenant (`/v1/admin/businesses`).  
   - Quick investor view: `/planner` serves the PLANNER.md HTML; `dashboard/planner.html` embeds it alongside owner/admin links.

3) Admin dashboard (optional)  
   - Open `dashboard/admin.html`; supply `X-Admin-API-Key`.  
   - Use Tenants, Usage, Twilio/Stripe health cards to verify config.

4) Self-service signup/onboarding (optional)  
   - Set `ALLOW_SELF_SIGNUP=true`; open `dashboard/signup.html` then `dashboard/onboarding.html` to connect calendar/email/QBO stubs.

5) Owner AI assistant  
   - Ask questions via the floating chat bubble.  
   - Rich answers require `SPEECH_PROVIDER=openai` and `OPENAI_API_KEY`; otherwise you get a metrics snapshot fallback.

Feature highlights
------------------
- Voice/chat assistant with deterministic emergency routing and optional OpenAI intent assist.
- Scheduling with Google Calendar; reschedule/cancel flows and SMS confirmations.
- CRM: customers, appointments, conversations, CSV import, retention campaigns.
- Owner/admin dashboards: schedules, callbacks/voicemails, analytics, Twilio/Stripe health.
- Self-service signup/onboarding, per-tenant API and widget tokens, subscription gating with grace and limits.
- Notifications: owner alerts for emergencies/missed calls/voicemail; customer reminders and opt-out handling.
- QuickBooks: sandbox/demo by default; set `QBO_CLIENT_ID`, `QBO_CLIENT_SECRET`, `QBO_REDIRECT_URI` (and `QBO_SANDBOX=false` for production) to enable live OAuth and syncing customers/receipts from appointments.

Architecture (capsule)
----------------------
- **Backend**: FastAPI, pluggable STT/TTS and intent (heuristics with optional OpenAI), repositories for appointments/conversations/customers.  
- **Dashboards**: static HTML/JS (`dashboard/index.html`, `dashboard/admin.html`) using `X-API-Key`, `X-Owner-Token`, `X-Admin-API-Key`.  
- **Widget**: `widget/chat.html` + `widget/embed.js` using `X-Widget-Token`.  
- **Integrations**: Google Calendar, Twilio/SMS, Stripe, QBO, Gmail—all stubbed by default via env profiles (`env.*.stub`) with signature verification where applicable.

Safety, auth, and billing
-------------------------
- Secrets via env vars; stubs avoid real calls in dev/CI.  
- Auth: bcrypt passwords, JWT access/refresh, lockout/reset, rate limits.  
- Subscription enforcement: `ENFORCE_SUBSCRIPTION=true` blocks voice/chat when not active/trialing; grace reminders and plan caps included.  
- Retention: periodic purge (`RETENTION_PURGE_INTERVAL_HOURS`), transcript capture is configurable (`capture_transcripts`, per-tenant retention opt-out).  
- Webhooks: Twilio/Stripe signature verification and replay protection; owner/admin tokens required in prod (`OWNER_DASHBOARD_TOKEN`, `ADMIN_API_KEY`, `REQUIRE_BUSINESS_API_KEY=true`).  
- Twilio webhook tuning: `STREAM_DEDUPE_TTL_SECONDS` (default 600s) and `SMS_EVENT_DEDUPE_TTL_SECONDS` (default 300s) control duplicate drop windows for media streams and SMS event IDs; optional per-number throttles via `SMS_PER_NUMBER_PER_MINUTE` and `SMS_PER_NUMBER_BURST`; enable `VERIFY_TWILIO_SIGNATURES=true` with `TWILIO_AUTH_TOKEN` in prod.  
- Rate-limit anomaly tuning: set `RATE_LIMIT_ANOMALY_THRESHOLD_BUSINESS` / `RATE_LIMIT_ANOMALY_THRESHOLD_IP` to emit alerts on spikes; `RATE_LIMIT_ANOMALY_THRESHOLD_5XX` for per-route error bursts.  
- Rate-limit defaults & tuning: global defaults are `RATE_LIMIT_PER_MINUTE=120` and `RATE_LIMIT_BURST=20`; per-number SMS throttles are disabled unless set (e.g., `SMS_PER_NUMBER_PER_MINUTE=6`, `SMS_PER_NUMBER_BURST=3` as a safe prod starting point). In dev/local, you can relax with `RATE_LIMIT_DISABLED=true`; in prod keep limits on and set anomaly thresholds for alerting.  
- Security anomalies surfaced via `/v1/admin/security/anomalies` and the admin dashboard card: counters for signature failures, invalid auth spikes, rate-limit blocks (IP/tenant/phone), and replay/verification events.  
- Recent security events (per tenant/time window) available at `/v1/admin/security/events` for admin triage.  
- Logs: structured JSON/plain logs carry `request_id`, `business_id`, and Twilio `call_sid`/`message_sid` when present to aid correlation in central logging.  
- Alerting: configure webhook and latency alerts via `TWILIO_WEBHOOK_FAILURE_ALERT_THRESHOLD`, `BILLING_WEBHOOK_FAILURE_ALERT_THRESHOLD`, and `LATENCY_ALERT_THRESHOLD_MS` (defaults off). See `docs/LOGGING_AND_ALERTING.md` for forwarding and runbook pointers.  
- Session store: defaults to in-memory; enable shared sessions across replicas with `SESSION_STORE_BACKEND=redis` (or simply set `REDIS_URL` to auto-prefer Redis) pointing to your Redis instance.  
- Error tracking (optional): set `SENTRY_DSN` (and optional `SENTRY_TRACES_SAMPLE_RATE`) to enable Sentry with PII-scrubbing headers; left disabled by default.
- Synthetic uptime: `python scripts/uptime_check.py --base http://localhost:8000` exercises `/healthz`, `/readyz`, widget start, Twilio SMS stub, and admin anomalies (set `OWNER_TOKEN`/`ADMIN_API_KEY` env for auth calls).
- Backups/DR (SQLite dev/stub): `python backend/scripts/backup_db.py --db ./backend/app.db --out ./backups`; restore with `python backend/scripts/backup_db.py restore --db ./backend/app.db --backup <file>`. Prune old backups with `python backend/scripts/prune_backups.py --dir ./backups --keep 10`. Validate by restoring into a clean env and exercising voice/chat/scheduling flows.
- K8s dev/stub automation: see `docs/k8s/sqlite-backup-and-prune.yaml` for combined backup+prune CronJobs (adjust PVC names, KEEP env).
- DR drill helper (SQLite dev/stub): `python backend/scripts/dr_drill.py --backup ./backups/app-<ts>.db --out ./tmp/dr_report.json` to restore into a temp DB, run smoke counts, and capture RPO estimate.

Performance & load smoke (CI)
-----------------------------
- `tests/test_perf_smoke.py` – baseline perf for core flows.  
- `tests/test_perf_multitenant_smoke.py` – multi-tenant path checks under load.  
- `tests/test_perf_transcript_smoke.py` – long transcript handling.  
- `tests/test_twilio_streaming_canary.py` – streaming canary (respects env secrets).  
These run in `.github/workflows/perf-smoke.yml` on every push/PR.

Testing & coverage
------------------
- Coverage enforced at 85% in Backend CI; artifacts (`coverage.xml`) per Python version are uploaded in Actions → backend-ci artifacts.  
- Lint/type/security: `ruff check .`, `black --check .`, `mypy`, `bandit`.  
- Core suites: `pytest` (full), `tests/test_business_admin.py` for admin health (Twilio/Stripe), `tests/test_intent_and_retention.py` for safety/transcript opts, `tests/test_subscription_guardrails.py` for gating/limits.  
- Providers are mocked/stubbed by default via `env.*.stub`; Twilio/Stripe/Google/QBO keys are never required to run tests locally or in CI.

Docs & references
-----------------
- Product and policy: `WIKI.md`, `CHANGELOG.md`, `RELEASES.md`, `SECURITY.md`, `PRIVACY_POLICY.md`, `TERMS_OF_SERVICE.md`, and the Bristol PDFs (`Bristol_Plumbing_*.pdf`, `Project_Engineering_Whitepaper.pdf`).  
- Architecture and deployment: `backend/BACKEND.md`, `dashboard/DASHBOARD.md`, plus platform details in `WIKI.md`.  
- ISMS and ISO prep: `docs/ISMS/ISMS_README.md` (links to scope, risk method, SoA, access control, secure SDLC, incident/DR, backups, logging/alerts, vendor register, and audit plan).  
- Incident playbooks: `docs/ISMS/INCIDENT_RESPONSE_PLAN.md` and the wiki playbooks (`ai_telephony_service_crm.wiki.local/IncidentPlaybooks.md`).  
- Beta tracking (archived): `docs/archive/beta/BETA_GITHUB_ISSUES_TASKLIST.md` (issue checklist), `docs/archive/beta/BETA_DOD.md` (Definition of Done), and `docs/archive/beta/BETA_KPIS.md` (top metrics).

New in this iteration
---------------------
- Subscription enforcement improved: grace reminders, plan cap warnings, and voicemail/callback surfacing on dashboard cards.  
- Perf smoke and coverage badges visible; README streamlined for faster onboarding.  
  - Coverage badge links to backend-ci; detailed `coverage.xml` per Python version is available in Actions → backend-ci artifacts.
- Investor brief available at `/planner` and `dashboard/planner.html`.
