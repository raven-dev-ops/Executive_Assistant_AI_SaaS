System Outline
==============

This repo contains a multi-tenant AI telephony assistant and lightweight CRM for small trades
businesses. The backend is the source of truth; dashboards and the chat widget are thin clients.

Components
----------
- Backend (`backend/`): FastAPI service providing voice/SMS/web chat + CRM + integrations.
- Dashboards (`dashboard/`): static HTML/JS owner + admin dashboards.
- Widget (`widget/`): embeddable chat widget (HTML + `embed.js`).
- Frontend (`frontend/`): Vite/React app (optional; separate from the static dashboards).
- Ops/infra (`k8s/`, `ops/`, `.github/workflows/`): deployment and operational automation.

Core Data And Tenancy
---------------------
- Tenancy is keyed by `business_id`.
- Requests typically identify the tenant via one of:
  - `X-API-Key` (tenant API key)
  - `X-Widget-Token` (public widget token)
  - `X-Owner-Token` (owner dashboard token)
  - `X-Admin-API-Key` (admin API key)
  - `X-Business-ID` (dev convenience header; not recommended for production)

Primary Flows
-------------
- Inbound call:
  - Twilio webhook -> backend -> conversation flow -> schedule -> confirmations + owner alerts.
- Web chat:
  - Widget -> backend chat API -> CRM conversation/history -> owner follow-up queue.
- Owner dashboard:
  - Reads owner KPIs, schedules, callbacks, conversations, exports; can toggle tenant lockdown.
- Admin dashboard:
  - Manages tenants, keys/tokens, and integration health checks.

Integrations (Stub-First)
-------------------------
- Twilio (voice/SMS): webhooks with signature verification + replay/idempotency protection.
- Calendar (Google Calendar): OAuth tokens per tenant; stubbed by default in dev.
- Billing (Stripe): webhooks with signature verification; stubbed by default in dev.
- Accounting (QuickBooks): OAuth + sync; stubbed by default in dev.
- Email (Gmail/SendGrid): provider abstraction; stubbed by default in dev.
- Speech (STT/TTS, intent): provider abstraction with deterministic fallbacks.

Reference Docs
--------------
- `README.md`: quick start + high-level feature overview.
- `backend/BACKEND.md`: backend-specific operational notes.
- `dashboard/DASHBOARD.md`: dashboard cards and the endpoints they call.
- `WIKI.md`: deeper domain/use-case context and deployment notes.
- `docs/ISMS/ISMS_README.md`: security/compliance program docs.

