SQLite Backup Cron (dev/stub)
-----------------------------

Example CronJob for environments that persist SQLite (dev/stub). Adjust PVC names and schedule as needed.

- Manifest: `docs/k8s/sqlite-backup-cron.yaml`
- Schedule: every 6 hours (`0 */6 * * *`)
- Command: `python backend/scripts/backup_db.py --db backend/app.db --out /backups`
- Volumes: `app-pvc` (workspace) and `backups-pvc` (backup storage).

Notes:
- Not intended for production (use managed DB backups instead).
- Rotate/prune old backups on the backup PVC if space is constrained. A simple approach: run a daily job to keep the latest N files (e.g., `find /backups -type f -mtime +7 -delete`).
- See also `sqlite-backup-prune-cron.yaml` for a daily prune CronJob (keeps newest N files with `KEEP` env).
