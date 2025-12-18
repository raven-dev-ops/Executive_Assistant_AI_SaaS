Disaster Recovery & Business Continuity
======================================

Objectives
----------
- **RPO**: <= 15 minutes for production databases.
- **RTO**: <= 60 minutes for backend API and dashboards.

Strategy
--------
- **Data**: Cloud SQL automated backups + point-in-time recovery; daily exports to secure bucket with 30-day retention. Local SQLite (dev/CI) is non-production and excluded.
- **App**: Immutable container images stored in Artifact Registry; redeployable to new Cloud Run service/region with environment variables and secrets from Secret Manager.
- **Configs/Secrets**: Stored in GitHub Actions secrets and Google Secret Manager; rotation tracked in access log; no secrets in repo.
- **Dependencies**: Twilio/Stripe/Google availability monitored; failover modes include SMS/email fallbacks and stub providers for non-prod.

Procedures
----------
- Maintain a DR runbook covering: retrieving latest backup, restoring to staging, validating app health checks, and promoting to production (see `DR_RUNBOOK.md`).
- Include health checks for: Twilio webhook endpoints, Calendar writes, owner notification hub, and auth issuance.
- Quarterly DR drill: restore from backup to staging, run smoke/perf suites, and record timings (RPO/RTO) in `BACKUP_AND_RESTORE.md`.

Communications
--------------
- IC informs stakeholders on DR activation; customer updates every 30-60 minutes until recovery.
- Post-DR review feeds into risk register and control improvements.
