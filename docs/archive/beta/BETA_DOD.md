Closed Beta Definition of Done
==============================

Entry criteria
--------------
- P0 reliability/security items shipped and verified in CI: rate limiting/abuse (#89), webhook signature enforcement (#88), structured logging/correlation IDs (#85), token hygiene/rotation (#84), owner notification reliability (#79), emergency detection v1.1 (#78), calendar correctness (#80), reschedule/cancel flows (#81), and self-service onboarding to ready-to-take-calls (#82).
- Smoke/perf suites green (`.github/workflows/perf-smoke.yml`) and coverage >=85% in Backend CI.
- Twilio/Stripe webhooks running with signature verification; stubs enabled in lower environments.
- Owner alerting hub active with SMS retry + email fallback; metrics exposed at `/v1/admin/owner-metrics`.

Customer experience
-------------------
- Voice/chat assistant routes emergencies deterministically and instructs callers to dial 911 when appropriate.
- Scheduling proposes correct slots and writes to Google Calendar; conflicts detected; opt-outs honored.
- Missed call/voicemail fallback creates callbacks and alerts the owner.
- Subscription gating: non-paying tenants see graceful degradation with reminders.

Supportability
--------------
- Logs are structured with request IDs; alerts configured for Twilio/webhook/auth/scheduling paths (see `docs/ISMS/LOGGING_AND_ALERTS.md`).
- Runbooks/playbooks available (`docs/ISMS/INCIDENT_RESPONSE_PLAN.md`, wiki IncidentPlaybooks).
- Risk register current for beta scope (`docs/ISMS/RISK_METHOD.md`).

Exit criteria (ready to graduate)
---------------------------------
- Zero open P0/P1 issues for 14 days.
- DR drill completed in last quarter with RPO <=15m and RTO <=60m (see `docs/ISMS/BACKUP_AND_RESTORE.md`).
- Access review completed in last 30 days; SSO/MFA enforced for GitHub/CI/Cloud.
