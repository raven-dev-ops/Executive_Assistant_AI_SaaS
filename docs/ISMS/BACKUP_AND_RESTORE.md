Backups and Restore Testing
===========================

Scope
-----
- Databases: Cloud SQL Postgres (authoritative source of truth for tenants, customers, appointments, audit/security events).
- Object storage: GCS dashboard assets bucket (configured via `GCS_DASHBOARD_BUCKET`).
- Third-party storage (out of scope for platform-managed backups): Twilio call/voicemail recordings (the app stores metadata + URLs).
- Secrets/config: Secret Manager and GitHub secrets are provider-managed; do not store secret values in backups.

Backup implementation
---------------------
- Cloud SQL automated backups and point-in-time recovery (PITR) must be enabled for the production instance.
- Additional logical export (recommended): periodic SQL export to a dedicated GCS backup bucket.
  - Script: `ops/cloudsql/export-sql.ps1` (see `ops/cloudsql/README.md`).
  - Optional automation: `.github/workflows/cloudsql-export-backup.yml` (requires GCP secrets configured in GitHub).
- Retention policy:
  - Cloud SQL: configured retention for automated backups + transaction logs.
  - GCS backup bucket: object versioning enabled and lifecycle deletion (example: delete objects older than 30 days).
    - Example command: `gsutil lifecycle set ops/gcs/lifecycle-delete-after-30d.json gs://YOUR_BACKUP_BUCKET`

Testing (quarterly)
-------------------
- Restore latest backup to staging Cloud SQL (one-command restore is in `DR_RUNBOOK.md`).
- Deploy backend to staging against the restored DB.
- Validate core integrity (health, auth gates, tenant isolation, scheduling reads) using the checklist in `DR_RUNBOOK.md`.
- Record RPO (backup timestamp vs. restore point) and RTO (start of restore to app healthy) in `BACKUP_RESTORE_LOG.md`.

Restore log (sample)
--------------------
| Date | Backup timestamp | RPO (min) | RTO (min) | Notes | Owner |
| --- | --- | --- | --- | --- | --- |
| 2025-12-12 | 2025-12-12 02:00 UTC | 10 | 42 | Restore to staging, smoke/perf suites passed | Eng |

Action items
------------
- Automate export scheduling (Cloud Scheduler/Cloud Run job or equivalent) and document where it is configured.
- Add/verify alerts for failed Cloud SQL backups and backup bucket object age > 36 hours.
