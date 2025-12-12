Logging, Monitoring, and Alert Rules
====================================

Central log pipeline
--------------------
- Emit structured key/value logs from backend (`backend/app/logging_config.py`) with request IDs and correlation IDs; ship stdout to the log sink (e.g., Cloud Logging or Datadog). JSON formatting can be added at the collector if needed.
- Normalize fields: `severity`, `tenant`, `request_id`, `call_sid`, `webhook_event`, `auth_principal`, `customer_phone`, `status`.
- Retention: 30 days for standard logs; 90 days for security/audit logs (webhooks/auth/access).

Alert rules (P0 focus)
----------------------
- **Twilio webhooks**: Error rate > 1% over 5 minutes OR signature verification failures > 5/min → page IC + owner email/SMS.
- **Scheduling/Calendar**: Consecutive failures writing events or zero available slots for active hours → page IC; include business id + requested slot window.
- **Auth**: JWT refresh failures > threshold, repeated login failures per IP/user > 10/min → alert and temporarily block IP/user.
- **Owner notifications**: SMS delivery failure without retry success, or fallback email used > 3 times in 15 minutes → notify owner + IC.
- **Stripe webhooks**: Signature verification failures or repeated 500s → alert and pause billing actions until resolved.

Dashboards
----------
- Create P0 dashboard panels for the above metrics; include red/amber/green thresholds and links to runbooks.
- Use existing metrics endpoints (`/metrics`) and owner notification status (`/v1/admin/owner-metrics`) as sources.

Runbooks and escalation
-----------------------
- Link alerts to playbooks in `INCIDENT_RESPONSE_PLAN.md` and `ai_telephony_service_crm.wiki.local/IncidentPlaybooks.md`.
- Escalation order: IC → backup engineer → product lead → executive sponsor.
- Post-alert actions: for each P0 alert, create an incident doc even if auto-recovered.
