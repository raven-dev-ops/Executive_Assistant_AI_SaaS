Backups and Restore Testing
===========================

Plan
----
- **Databases**: Cloud SQL automated backups nightly; PITR enabled. Weekly export to GCS (`gs://ai-telephony-backups/`) with 30-day retention.
- **Configs**: GitHub Actions secrets and Google Secret Manager backups handled by providers; export list of secrets monthly for review (no secret values stored).
- **Dashboards/assets**: GCS bucket versioning enabled; weekly checksum report.

Testing (quarterly)
-------------------
- Restore latest backup to staging Cloud SQL.
- Deploy backend to staging (new instance) with restored DB; run `python -m pytest backend/tests/test_twilio_integration.py backend/tests/test_calendar_conflicts.py backend/tests/test_conversation.py`.
- Validate: owner notification hub works (SMS retry + email fallback), webhook signatures enforced, scheduling creates events, auth tokens issued.
- Record RPO (backup timestamp vs. restore point) and RTO (start of restore to app healthy) in the log below.
- For local dev/stub SQLite: `python backend/scripts/backup_db.py --db ./backend/app.db --out ./backups` and restore with `python backend/scripts/backup_db.py restore --db ./backend/app.db --backup <file>`.
- DR drill helper (SQLite dev/stub): `python backend/scripts/dr_drill.py --backup ./backups/app-<ts>.db --out ./tmp/dr_report.json` to restore into a temp DB, run basic smoke counts, and capture RPO estimate.

Restore log (sample)
--------------------
| Date | Backup timestamp | RPO (min) | RTO (min) | Notes | Owner |
| --- | --- | --- | --- | --- | --- |
| 2025-12-12 | 2025-12-12 02:00 UTC | 10 | 42 | Restore to staging, smoke/perf suites passed | Eng |

Action items
------------
- Automate backup verification in CI (import scrubbed dump, run smoke suite).
- Add alert for failed Cloud SQL backups and bucket object age > 36 hours.
