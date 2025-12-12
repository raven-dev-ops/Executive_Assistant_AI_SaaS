Closed Beta KPIs
================

Reliability
-----------
- P0 alert MTTA/MTTR (Twilio/webhook/auth/scheduling): MTTA < 5 min, MTTR < 60 min.
- Owner notification success rate (SMS or fallback email): >= 99%.
- Webhook signature verification failure rate: < 0.5% over 24h.

Product outcomes
----------------
- Booking conversion: % of inbound calls that result in a scheduled appointment within the call/session.
- Emergency handling accuracy: % of emergency-intent calls correctly tagged and routed; false negatives < 2%.
- Missed-call recovery: % of missed/voicemail events with owner callback created within 10 minutes.
- Return-customer recognition: % of repeat callers matched to existing customer record.

Quality
-------
- Test coverage: >= 85% (Backend CI) with zero failing smoke/perf suites.
- Regression escape rate: number of post-deploy incidents per release (goal: 0 P0/P1 in beta).

Growth/Usage (beta)
-------------------
- Active tenants per week; call volume per tenant; bookings per tenant.
- Time-to-first-value: time from signup to first scheduled appointment.
- Opt-out rate for SMS confirmations.

Where to see these
------------------
- GitHub Actions: backend-ci (coverage), perf-smoke (perf/smoke health), dependency/security scans.
- Metrics endpoints: `/metrics` and `/v1/admin/owner-metrics` (owner alerting status).
- Dashboards: owner/admin dashboards for schedules/callbacks/conversations; planner view for beta progress.
