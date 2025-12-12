ISMS Scope
==========

Scope statement
---------------
- **Product**: AI Telephony Service & CRM (voice/chat assistant, scheduling, CRM, billing).
- **Components in scope**: FastAPI backend (`backend/`), static dashboards (`dashboard/`, `widget/`, `dashboard_proxy/`), CI/CD workflows (`.github/workflows/*`), IaC/k8s manifests (`k8s/`), and data stores (Cloud SQL Postgres, optional SQLite for dev/test).
- **Data types**: Customer PII (names, phone, email, address), conversation transcripts/notes, calendar events, billing metadata (Stripe customer/subscription ids), limited payment link metadata (no PAN), OAuth tokens (Google Calendar/Gmail/QBO), webhook payloads (Twilio/Stripe).
- **Tenants/environments**: Prod, staging, and CI ephemeral environments. Local developer laptops are in-scope only for code and stub/test data; production data must not be stored locally.
- **Org units & people**: Engineering, QA, SRE/Operations, and product owners with GitHub access and deployment rights.

Exclusions
----------
- Third-party platforms (Stripe, Twilio, Google) are treated as supporting services; their internal controls are out of scope but assessed in the vendor register and DPAs.
- Customer-owned infrastructure (if self-hosted) is out of scope; responsibilities are captured in the shared-responsibility section of `TERMS_OF_SERVICE.md`.

Assets and boundaries
---------------------
- **Source**: GitHub repo `raven-dev-ops/ai_telephony_service_crm`, protected branches and required reviews.
- **Build/Deploy**: GitHub Actions plus Cloud Build/Cloud Run (see `WIKI.md` Platform Deployment) with artifact signing planned.
- **Runtime**: Cloud Run services (backend, dashboard proxy) and Cloud SQL Postgres; GCS bucket for dashboard assets; Twilio numbers/webhooks; Stripe webhooks; Google APIs for Calendar/OAuth.
- **Logging/Monitoring**: Central log pipeline described in `LOGGING_AND_ALERTS.md` with P0 alert rules for Twilio/webhooks/scheduling/auth.

Objectives
----------
- Protect customer and caller data (confidentiality).
- Ensure assistant availability for P0/P1 voice/webhook paths (availability).
- Maintain accurate scheduling, notifications, and billing (integrity).

Scope owner
-----------
- ISMS owner: Engineering Lead (acts as ISO coordinator), with deputies in SRE and Product for evidence and reviews.
