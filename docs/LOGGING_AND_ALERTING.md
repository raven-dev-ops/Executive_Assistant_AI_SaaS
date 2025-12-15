Logging & Alerting Guide
========================

Overview
--------
This backend emits structured logs (JSON or plain) that include `request_id`, `business_id`, and Twilio `call_sid`/`message_sid` where present. Use `LOG_FORMAT=json` in production to keep logs machine-friendly for shipping to your aggregator.

Log aggregation (example: Fluent Bit to Cloud Logging)
------------------------------------------------------
- Set `LOG_FORMAT=json` and ensure stdout is collected by your runtime.
- For Kubernetes, deploy Fluent Bit with a sink of your choice; example snippet for Cloud Logging:
  ```
  [SERVICE]
      Flush        5
      Parsers_File parsers.conf

  [INPUT]
      Name              tail
      Path              /var/log/containers/*.log
      Parser            docker
      Tag               kube.*

  [FILTER]
      Name              modify
      Match             kube.*
      Add               service ai-telephony-backend

  [OUTPUT]
      Name              stackdriver
      Match             kube.*
      Resource          k8s_container
  ```
- For Cloud Run/Cloud Functions, stdout/stderr is automatically shipped; set `LOG_FORMAT=json` to keep fields preserved.
- OTLP/Datadog/Loki: if you already ship OTLP from other services, set `LOG_FORMAT=json` and scrape stdout, or add an OTLP sidecar (e.g., OpenTelemetry Collector) to forward to Datadog/Loki/Elastic. Include `service` and `environment` labels from the JSON payload when mapping fields.

Central queries (tenant + call/message correlation)
---------------------------------------------------
- The JSON logger emits `request_id`, `business_id`, `call_sid`, and `message_sid`. Use these fields as structured labels in your log store.
- Example queries:
  - Google Cloud Logging: `resource.type="k8s_container" jsonPayload.business_id="biz-123" jsonPayload.call_sid:*`
  - Loki: `{service="ai-telephony-backend", business_id="biz-123"} |= "rate_limit_triggered"`
  - Datadog Log Explorer: `service:ai-telephony-backend business_id:biz-123 call_sid:* @level:error`
- Dashboard tips: add saved views for (a) per-tenant error rate, (b) Twilio signature failures grouped by `business_id`, (c) Stripe webhook errors grouped by `request_id` for replay investigations.
- Correlate with Sentry: Sentry tags include the same correlation fields so a log search on `request_id` will match the error event.

Alerting thresholds
-------------------
- Twilio webhooks: configure `TWILIO_WEBHOOK_FAILURE_ALERT_THRESHOLD` to trigger P0 when cumulative webhook errors reach the threshold (also fires immediately on 5xx).
- Stripe webhooks: configure `BILLING_WEBHOOK_FAILURE_ALERT_THRESHOLD` for Stripe webhook errors.
- Latency SLO: set `LATENCY_ALERT_THRESHOLD_MS` (e.g., 3000) and optional `LATENCY_ALERT_PATHS` (comma-separated prefixes, default `/v1/voice,/v1/chat,/v1/widget`) to fire P0 when exceeded.
- Rate limit anomalies: `RATE_LIMIT_ANOMALY_THRESHOLD_BUSINESS`, `RATE_LIMIT_ANOMALY_THRESHOLD_IP`, `RATE_LIMIT_ANOMALY_THRESHOLD_5XX` already gate spike alerts.
- Error-rate spikes: `RATE_LIMIT_ANOMALY_THRESHOLD_5XX` triggers P1 `error_rate_spike` per route; set low in staging to validate and higher in prod.
- Error tracking: set `SENTRY_DSN` (and optionally `SENTRY_TRACES_SAMPLE_RATE`) to enable Sentry with PII-scrubbing on auth headers; keep unset in dev/stub. Sentry scope tags include `request_id`, `business_id`, `call_sid`, and `message_sid` for correlation.

Runbooks
--------
Runbook links are embedded in alerts for Twilio webhooks, Stripe webhooks, latency SLO breaches, and notification failures. Host them in your wiki/ops playbooks (defaults point to `wiki/Runbooks#...`). Keep instructions updated for triage, rollback, and escalation.

Validating correlation fields
-----------------------------
- With `LOG_FORMAT=json`, issue a Twilio SMS webhook (or call) via ngrok/tunnel and inspect the resulting log: you should see `business_id`, `call_sid` (voice), or `message_sid` (SMS) populated alongside `request_id`.
- For non-Twilio requests (e.g., `/v1/chat`), `business_id` will be set when headers include `X-Business-ID`/`X-API-Key`; otherwise it remains `-`.

Simulating alert firing (staging)
---------------------------------
- Twilio webhook failure: set `TWILIO_WEBHOOK_FAILURE_ALERT_THRESHOLD=1` and POST to `/twilio/sms` without `X-Twilio-Signature`; expect P0 `twilio_webhook_failure`.
- Stripe webhook failure: set `BILLING_WEBHOOK_FAILURE_ALERT_THRESHOLD=1` and POST to `/v1/billing/webhook` with an invalid `Stripe-Signature`; expect P0 `billing_webhook_failure`.
- Latency SLO: set `LATENCY_ALERT_THRESHOLD_MS=1` temporarily and hit `/v1/chat`; expect P0 `latency_slo_breach`.
- 5xx spike: set `RATE_LIMIT_ANOMALY_THRESHOLD_5XX=1` and force an error on a route; expect P1 `error_rate_spike`.
