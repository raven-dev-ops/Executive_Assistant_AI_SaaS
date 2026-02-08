Deployment Checklist
====================

This checklist is intended for staging/prod deployments.

Pre-Deploy
----------
- Confirm required secrets are present in the secret manager and wired into the runtime.
- Confirm environment variables match the target environment (`ENVIRONMENT=staging|prod`).
- Confirm DB connectivity and migrations:
  - `alembic upgrade head`
- Confirm webhook verification is enabled for production-like envs:
  - Twilio signature verification
  - Stripe signature verification + replay protection
- Confirm rate limiting is enabled and thresholds are sane.

Post-Deploy
-----------
- Verify:
  - `/healthz` returns 200
  - `/readyz` returns ok (and DB is healthy if enabled)
  - `/metrics/prometheus` is reachable for alerting checks (and authenticated if required)
- Exercise smoke paths:
  - Widget bootstrap (`/v1/widget/business`)
  - Owner schedule summary
  - Admin health cards

Operational Readiness
---------------------
- Logging/alerts: `docs/ISMS/LOGGING_AND_ALERTS.md`
- Backups/restore: `docs/ISMS/BACKUP_AND_RESTORE.md`
- Incident response: `docs/ISMS/INCIDENT_RESPONSE_PLAN.md`

