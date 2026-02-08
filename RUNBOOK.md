Operations Runbook
==================

This runbook focuses on practical operator actions. For policy-level requirements, see `SECURITY.md`
and `docs/ISMS/*`.

Local Smoke Checks
------------------
1. Start backend:
   - `cd backend`
   - `uvicorn app.main:app --reload --env-file ..\\env.dev.inmemory`
2. Validate:
   - `GET http://localhost:8000/healthz`
   - `GET http://localhost:8000/metrics/prometheus`
3. Open dashboards:
   - `dashboard/index.html`
   - `dashboard/admin.html`

Common Production Checks
------------------------
- Health endpoints: `/healthz` and `/readyz`
- Metrics: `/metrics` and `/metrics/prometheus`
- Webhook signature verification:
  - Twilio: `VERIFY_TWILIO_SIGNATURES=true` in prod-like envs
  - Stripe: signature verification required in prod-like envs

Alerts And Incident Handling
----------------------------
- Alert definitions and thresholds: `docs/ISMS/LOGGING_AND_ALERTS.md`
- Incident process: `docs/ISMS/INCIDENT_RESPONSE_PLAN.md`
- Incident template: `docs/ISMS/INCIDENT_TEMPLATE.md`

Backups And Restore
-------------------
- Procedure: `docs/ISMS/BACKUP_AND_RESTORE.md`
- DR plan: `docs/ISMS/DR_BCP.md`
- DR runbook: `docs/ISMS/DR_RUNBOOK.md`

