# Closed Beta Definition of Done (DoD)

Use this checklist to decide if the product is **beta-ready**. Items are scoped to the reference tenant unless stated otherwise. For anything marked "Fail", the beta is **not** ready.

## Functional readiness
- [ ] Voice/chat assistant: schedule, reschedule, cancel, FAQ, emergency flows verified with stub providers.
- [ ] Emergency handling: deterministic routing, owner notification works (SMS + fallback email), callback queue populated.
- [ ] Scheduling: no double-booking; calendar writes succeed or fail atomically; confirmations sent (SMS/email when configured).
- [ ] Callback/voicemail: items are actionable in the dashboard (resolve/refresh) and owner can return calls with context.
- [ ] Onboarding: new tenant can be provisioned without manual DB edits; guided setup for Twilio/Calendar/Gmail completes.

## Non-functional gates (pass/fail)
- **Security**: webhook signatures enforced in prod; JWT/role checks on owner/admin paths; PII redaction in logs/transcripts verified.
- **Performance**: perf smoke suite passes; streaming voice latency within target; no request class above SLO error budget.
- **Uptime**: health/readiness endpoints green; no blocking reliance on optional providers (graceful degradation defined).
- **Data retention**: retention purge job runs; opt-out respected for transcripts/SMS; exports/deletes auditable.
- **Subscription**: degraded-but-safe behavior defined and enforced when inactive (voicemail/callback only, emergencies still reach owner).

## Known limitations (acceptable for closed beta)
- Gmail/Calendar/Twilio may run in stub mode for demos; live keys required for real delivery.
- Advanced analytics (LTV, forecasting) are out of scope; only core KPIs and callback metrics are available.
- Chaos/failure injection limited to staging; not exposed in prod/beta tenants.
- Multi-tenant load is light; horizontal scaling patterns are not yet hardened.

## How to use
- Must be linked from README and PLANNER for quick access.
- Dashboard planner view should link directly to this file.
- CI should include or reference the DoD when running smoke checks.
