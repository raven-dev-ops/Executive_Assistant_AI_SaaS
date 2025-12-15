DR Drill Playbook (SQLite dev/staging)
======================================

Objective
---------
Validate backups by restoring into a clean environment and capturing RPO/RTO plus smoke test results.

Pre-reqs
--------
- Backup file available (for SQLite dev/stub): `./backups/app-<ts>.db`
- Python deps installed; working from repo root.

Steps
-----
1) Restore into temp location and run drill helper:
   ```bash
   python backend/scripts/dr_drill.py --backup ./backups/app-latest.db --out ./tmp/dr_report.json
   ```
   - This restores to a temp DB, runs basic counts, and outputs RPO estimate.
2) Point the app at the temp DB (if desired for UI validation):
   ```bash
   export DATABASE_URL=sqlite:///./tmp/dr_drill.db
   uvicorn app.main:app --reload --env-file ./env.dev.db
   ```
3) Run smoke tests against the restored DB:
   ```bash
   cd backend
   pytest tests/test_twilio_integration.py tests/test_calendar_conflicts.py tests/test_conversation.py
   ```
4) Record RPO/RTO and results in `docs/ISMS/BACKUP_RESTORE_LOG.md` (include backup timestamp, restore start/end, tests run, and any issues).

Prod/Cloud SQL drill (outline)
------------------------------
- Restore latest backup to staging/DR instance via Cloud SQL (or your managed DB equivalent).
- Run a minimal smoke suite (voice/chat/twilio/webhook) against the restored instance.
- Capture RPO (backup age) and RTO (restore+validation duration); log evidence.

Validation
----------
- Health checks (`/healthz`, `/readyz`) pass on restored environment.
- Twilio/Stripe webhook signature enforcement remains enabled (prod/staging).
- Rate limits and tenant isolation flags remain intact.
- Smoke tests pass; any failures are documented and fixed.
