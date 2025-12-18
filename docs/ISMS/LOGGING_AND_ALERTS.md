Logging, Monitoring, and Alert Rules
====================================

Central log pipeline
--------------------
- Emit structured key/value logs from backend (`backend/app/logging_config.py`) with request IDs; ship stdout to the log sink (e.g., Cloud Logging or Datadog). Set `LOG_FORMAT=json` for JSON output from the app if the collector does not normalize plain text.
- Normalize fields: `severity`, `tenant`, `request_id`, `call_sid`, `webhook_event`, `auth_principal`, `customer_phone`, `status`.
- Retention: 30 days for standard logs; 90 days for security/audit logs (webhooks/auth/access).

Log schema (JSON)
-----------------
When `LOG_FORMAT=json` is enabled, logs are emitted as JSON to stdout (Cloud Run picks these up automatically in Cloud Logging).

Required correlation fields (best-effort):
- `request_id`: generated per request (or propagated from `X-Request-ID`).
- `trace_id`: extracted from `X-Cloud-Trace-Context` / `traceparent` when available.
- `business_id`: tenant id (from `X-Business-ID`, `?business_id=...`, or resolved from API/widget/JWT where applicable).
- `call_sid`: Twilio voice call id (when available).
- `message_sid`: Twilio message id (when available).

Query examples (Cloud Logging)
-----------------------------
- By tenant: `jsonPayload.business_id="biz_123"`
- By call: `jsonPayload.call_sid="CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"`
- By message: `jsonPayload.message_sid="SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"`
- By request: `jsonPayload.request_id="..."`

Alert rules (P0 focus)
----------------------
- **Twilio webhooks**: Error rate > 1% over 5 minutes OR signature verification failures > 5/min -> page IC + owner email/SMS.
- **Scheduling/Calendar**: Consecutive failures writing events or zero available slots for active hours -> page IC; include business id + requested slot window.
- **Auth**: JWT refresh failures > threshold, repeated login failures per IP/user > 10/min -> alert and temporarily block IP/user.
- **Owner notifications**: SMS delivery failure without retry success, or fallback email used > 3 times in 15 minutes -> notify owner + IC.
- **Stripe webhooks**: Signature verification failures or repeated 500s -> alert and pause billing actions until resolved.
- **Latency SLO (voice/chat)**: sustained p95 latency breach (e.g., > 2s chat, > 4s conversation) -> alert IC; check recent deploys and upstream providers.

Implementation (stack)
----------------------
- **Notification channel**: `P0 Alerts Email` (damon.heath@ravdevops.com) is the active path today; Slack/PagerDuty are not configured.
- **Cloud Logging (Cloud Run default)**: Backend stdout/err flows into Cloud Logging. Set env `LOG_FORMAT=json` in prod for structured payloads. Create logs-based metrics and alerting policies (examples below) via `gcloud` or the console.
  - Example logs-based metric filter (Twilio webhook failures):  
    `resource.type=\"cloud_run_revision\" AND labels.\"service_name\"=\"ai-telephony-backend\" AND textPayload:\"twilio_webhook_failure\"`
  - Alert policy CLI pattern (adjust metric and threshold):  
    `gcloud alpha monitoring policies create --display-name=\"P0 Twilio webhook failures\" --condition-display-name=\"webhook failures\" --condition-filter=\"metric.type=\"logging.googleapis.com/user/twilio_webhook_failure\"\" --condition-compare=COMPARISON_GT --condition-threshold-value=5 --condition-duration=300s --notification-channels=<channel-ids>`
- **Prometheus-style checks via GitHub Actions**: `.github/workflows/p0-alerts.yml` polls the `/metrics/prometheus` endpoint every 15 minutes. Configure repo secrets `METRICS_URL`, optional `METRICS_AUTH_HEADER`, thresholds (e.g., `TWILIO_WEBHOOK_THRESHOLD`, `CALENDAR_FAILURE_THRESHOLD`, `AUTH_FAILURE_THRESHOLD`, `OWNER_ALERT_FAILURE_THRESHOLD`), and optional `SLACK_WEBHOOK`. Workflow fails (and optionally posts to Slack) when thresholds are exceeded; in this repo the Slack hook is empty so failures surface via GitHub checks + email callbacks only.
- **Cloud Run 5xx alert (created)**: Alert policy `P0 Cloud Run 5xx (backend)` watches `run.googleapis.com/request_count` for `service_name=ai-telephony-backend` with `response_code_class=5xx`, threshold >0 over 5m, notifying channel `P0 Alerts Email` (damon.heath@ravdevops.com). Adjust notification channels as needed.
- **Twilio webhook alert (created)**: Logs-based metric `twilio_webhook_failures` (resource.type=cloud_run_revision, service=ai-telephony-backend, textPayload contains twilio_webhook_failure) with alert policy `P0 Twilio webhook failure` (threshold >0, immediate) notifying `P0 Alerts Email`.
- **Cloud SQL backup alert (created)**: Logs-based metric `cloudsql_backup_errors` (resource.type=cloudsql_database, severity>=ERROR with backup text/protoPayload) and alert policy `P0 Cloud SQL backup error` (threshold >0, immediate) notifying `P0 Alerts Email`.

Dashboards
----------
- Create P0 dashboard panels for the above metrics; include red/amber/green thresholds and links to runbooks.
- Use existing metrics endpoints (`/metrics`) and owner notification status (`/v1/admin/owner-metrics`) as sources.

Runbooks and escalation
-----------------------
- Link alerts to playbooks in `INCIDENT_RESPONSE_PLAN.md` and `ai_telephony_service_crm.wiki.local/IncidentPlaybooks.md`.
- Escalation order: IC -> backup engineer -> product lead -> executive sponsor.
- Post-alert actions: for each P0 alert, create an incident doc even if auto-recovered.

P0 runbooks (triage steps)
--------------------------
Twilio webhook failure spike:
- Filter logs by `call_sid` / `request_id` and confirm whether failures are 401/409 (signature/replay) vs 5xx.
- Verify `TWILIO_AUTH_TOKEN` and `VERIFY_TWILIO_SIGNATURES` and confirm Twilio webhook URL matches the deployed base URL.
- Mitigation: temporarily relax signature enforcement only if required and paired with rate limiting + short TTL replay window.

Stripe webhook failures:
- Filter logs by `request_id` and check for signature mismatch vs internal 5xx.
- Verify `STRIPE_WEBHOOK_SECRET` matches Stripe dashboard endpoint secret; confirm endpoint URL is current.
- Mitigation: if persistent 5xx, pause billing automation and process critical events manually until fixed.

Elevated 5xx rate:
- Check Cloud Run request logs for the top failing path(s); use `request_id`/`trace_id` to pivot into stack traces.
- Roll back to the previous Cloud Run revision if correlated with a deploy.

Latency SLO breach:
- Check p95 latency metrics (and Cloud Run request latency) and correlate with provider errors (OpenAI/GCP/Twilio/Google APIs).
- Mitigation: enable stub providers in staging, reduce concurrency, or roll back the latest revision.
