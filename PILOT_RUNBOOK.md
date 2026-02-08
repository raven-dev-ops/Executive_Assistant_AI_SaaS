Pilot Runbook
=============

Use this runbook when onboarding a pilot tenant.

1. Create/verify tenant
-----------------------
- Create the Business record (admin APIs / seed script).
- Issue the tenant API key and widget token.

2. Configure integrations (stubs first)
---------------------------------------
- Calendar: connect Google Calendar OAuth (or use stub in staging).
- Telephony: configure Twilio number and webhook URLs; verify signature settings.
- Billing: configure Stripe keys/webhook secret/prices; verify signature verification.

3. Validate end-to-end
----------------------
- Place a test call through Twilio (or stub) and confirm:
  - appointment can be created
  - confirmations/reminders honor opt-out behavior
  - emergencies trigger owner alerts
- Validate widget chat works from `widget/chat.html`.

4. Monitoring
-------------
- Confirm `/metrics/prometheus` is reachable for alert checks.
- Review logging and alert rules: `docs/ISMS/LOGGING_AND_ALERTS.md`.

