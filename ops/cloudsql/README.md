# Cloud SQL backup + restore (ops)

These scripts are intended for staging restores and DR drills against the Cloud SQL Postgres instance used by `ai_telephony_service_crm`.

## Prerequisites

- `gcloud` installed and authenticated (`gcloud auth login` or workload identity).
- IAM permissions:
  - Cloud SQL Admin (or least-privilege equivalent for backup/export/restore)
  - Storage Object Admin for the backup bucket (exports)
- A GCS bucket dedicated to backups (enable object versioning + lifecycle retention).
  - Example lifecycle config: `ops/gcs/lifecycle-delete-after-30d.json`
  - Apply: `gsutil lifecycle set ops/gcs/lifecycle-delete-after-30d.json gs://YOUR_BACKUP_BUCKET`

## Export SQL dump to GCS

Creates a compressed `.sql.gz` export via Cloud SQL export:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ops/cloudsql/export-sql.ps1 `
  -Instance ai-telephony-db `
  -Database ai_telephony `
  -Bucket ai-telephony-backups `
  -ProjectId YOUR_GCP_PROJECT_ID `
  -Offload
```

## Restore latest automated backup to staging

Restores the latest SUCCESS backup from `BackupInstance` into `RestoreInstance` and prints RPO/RTO timing:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ops/cloudsql/restore-latest-backup.ps1 `
  -BackupInstance ai-telephony-db `
  -RestoreInstance ai-telephony-staging `
  -ProjectId YOUR_GCP_PROJECT_ID `
  -TimeoutSeconds 7200 `
  -OutputJson restore-evidence.json
```

Notes:
- This overwrites the target instance data. Use a dedicated staging/DR instance.
- For a "restore into clean environment" drill, create a new instance first (or use a clone workflow) and point `-RestoreInstance` at that instance.
