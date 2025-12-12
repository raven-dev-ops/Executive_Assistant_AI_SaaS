Incident Response Plan
======================

Severity levels
---------------
- **P0**: Outage or data breach affecting production voice/webhook/auth paths; immediate pager and owner alert.
- **P1**: Degraded service with customer impact (delays in scheduling, delayed notifications).
- **P2**: Limited or no customer impact; handled in business hours.

Roles
-----
- Incident Commander (IC): Engineering lead on-call.
- Communications: Product/Customer lead.
- Scribe: Any responder capturing timeline in the incident doc.
- On-call rotation: Engineering/SRE weekly rotation; backup is product engineer familiar with Twilio/Stripe/Calendar.

Process
-------
1) Detect: Alerts from Twilio/webhook/scheduling/auth rules (see `LOGGING_AND_ALERTS.md`), or customer reports.  
2) Triage: Set severity, assign IC, open incident doc (template in `ai_telephony_service_crm.wiki.local/IncidentPlaybooks.md`).  
3) Mitigate: Stabilize (rate-limit, fail closed on webhooks, switch providers/stubs, reroute owner notifications).  
4) Communicate: Update status to stakeholders every 30-60 minutes; note customer impact.  
5) Eradicate/Recover: Root cause fix, validate via smoke/perf suites, confirm owner alerts and scheduling paths recovered.  
6) Post-incident: Publish postmortem within 72 hours; file follow-up issues and link to risk register.

Playbooks
---------
- **Twilio/Webhook outage**: Rate-limit, enable replay protection, fail closed on signature check; use email backup to owners; queue callbacks; switch to stub SMS for tests.  
- **Scheduling/Calendar errors**: Move to local queue; flag conflicting appointments; notify owners with manual booking steps; retry with exponential backoff.  
- **Auth/Token issues**: Rotate tokens (Stripe/Twilio/Google); revoke compromised tokens; invalidate dashboard tokens; enforce password resets if applicable.

Evidence
--------
- Store incident docs and postmortems in the wiki or shared drive; link follow-up GitHub issues and dates closed.
- Track MTTA/MTTR per incident and feed into risk reviews.
