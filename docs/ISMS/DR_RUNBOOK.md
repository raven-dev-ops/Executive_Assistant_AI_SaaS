Disaster Recovery Runbook (Cloud Run + Cloud SQL)
=================================================

Scope
-----
This runbook covers restoring the production Cloud SQL Postgres database for `ai_telephony_service_crm` into a staging/DR instance and validating that core app integrity is preserved.

Primary system components:
- Cloud Run service: `ai-telephony-backend`
- Cloud SQL Postgres instance: `ai-telephony-db` (database: `ai_telephony`)
- Dashboard assets: GCS bucket configured via `GCS_DASHBOARD_BUCKET`

Recovery objectives (targets)
-----------------------------
- RPO: <= 15 minutes
- RTO: <= 60 minutes (restore + deploy + basic validation)

Prerequisites
-------------
- Access: GCP IAM permissions to list backups and restore (Cloud SQL Admin, plus minimum required).
- Tooling: `gcloud` installed and authenticated.
- Dedicated restore target instance:
  - Staging restore instance (recommended): `ai-telephony-staging`
  - Or create a new DR drill instance (example): `ai-telephony-drill-YYYYMMDD`

Restore procedure (one command, staging first)
----------------------------------------------
WARNING: This overwrites the target instance data.

From repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ops/cloudsql/restore-latest-backup.ps1 `
  -ProjectId YOUR_GCP_PROJECT_ID `
  -BackupInstance ai-telephony-db `
  -RestoreInstance ai-telephony-staging `
  -TimeoutSeconds 7200 `
  -OutputJson restore-evidence.json
```

What to save as evidence:
- The `restore-evidence.json` file produced by the script (timestamps, backup id, operation id).
- Any console logs (copy/paste into the secure share) and the completed validation checklist below.

Validation checklist (post-restore)
-----------------------------------
Run these after the restored DB is in place and the staging backend is deployed against it.

- [ ] App health is green:
  - [ ] `GET /healthz` returns 200
  - [ ] `GET /readyz` returns 200
- [ ] Auth basics:
  - [ ] Admin routes require `X-Admin-API-Key`
  - [ ] Owner routes require `X-Owner-Token` (prod/staging)
- [ ] Tenant isolation:
  - [ ] Listing businesses works (admin)
  - [ ] Data is isolated by `X-Business-ID` (no cross-tenant leakage)
- [ ] Scheduling reads:
  - [ ] Owner schedule endpoints can read appointments
  - [ ] Calendar integration status endpoints load without errors

DR drill cadence
----------------
- Minimum: quarterly restore drill into staging or a dedicated DR instance.
- Record RPO/RTO and findings in `BACKUP_RESTORE_LOG.md`.

Communications templates
------------------------
Internal status update (every 30-60 minutes during DR):

Subject: DR in progress - ai-telephony (P0)

- Summary: Restoring Cloud SQL backup into staging/DR instance and validating backend integrity.
- Customer impact: [none/staging-only/prod degraded]
- Current phase: [restore running / deploy / validation]
- RPO estimate: [X minutes]
- ETA to next update: [time]
- Owner: [name]

Owner-facing message (if customer impact is expected):

Subject: Service recovery in progress

We are restoring service following an infrastructure event. Scheduling and messaging may be delayed during recovery. We will provide another update within 60 minutes. If you have urgent jobs, please use your direct line and continue manual scheduling until we confirm recovery.

