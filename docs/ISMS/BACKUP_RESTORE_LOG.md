Backup and Restore Evidence Log
===============================

Use this log to record each backup/restore drill with RPO/RTO measurements.

| Date | Environment | Backup Timestamp | RPO (minutes) | RTO (minutes) | Validation (tests run) | Issues Found | Actions | Evidence Link |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-12-12 | Staging | Not run (pending drill) | N/A | N/A | Not run | Drill not yet executed; automated Cloud SQL backups available (last success 2025-12-11 06:29 UTC). | Plan restore to staging + run smoke tests. | `gcloud sql backups list --instance=ai-telephony-db` (2025-12-12) |
| 2025-12-12 | DR drill (new instance) | 2025-12-11 06:29 UTC (backup id 1765432800000) | ~1532 (backup age) | ~6 (restore duration) | Not run | Restored backup to private Cloud SQL instance `ai-telephony-drill`; tests not run because instance is private-IP only and org policy blocks authorized networks/public IP. Need Cloud SQL Auth Proxy/PSC path to connect and run suite. | Provision private/PSC access for test runner (proxy or bastion) and rerun tests; then record results. | `gcloud sql backups restore ... --restore-instance=ai-telephony-drill` (success), `gcloud sql operations wait ce83c984-...` |

Checklist for each entry
------------------------
- Restore latest production backup to staging or DR environment.
- Run core tests: `pytest backend/tests/test_twilio_integration.py backend/tests/test_calendar_conflicts.py backend/tests/test_conversation.py`.
- Validate owner notification hub (SMS retry + email fallback) and webhook signature enforcement.
- Document RPO/RTO and attach logs/screenshots as evidence.
