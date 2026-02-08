API Reference (High Level)
==========================

The backend exposes an OpenAPI spec and interactive docs:
- `GET /openapi.json`
- `GET /docs`

Authentication And Tenant Resolution
------------------------------------
Common headers:
- `X-API-Key`: tenant API key (most tenant-scoped APIs)
- `X-Owner-Token`: owner dashboard token (owner APIs)
- `X-Admin-API-Key`: admin APIs
- `X-Widget-Token`: public chat widget

Development-only convenience:
- `X-Business-ID`: tenant id override (do not rely on this for production)

Health And Metrics
------------------
- `GET /healthz`: basic liveness check
- `GET /readyz`: readiness (optionally checks DB)
- `GET /metrics`: JSON metrics snapshot
- `GET /metrics/prometheus`: minimal Prometheus text-format metrics used by alert checks

Major Route Groups (Non-Exhaustive)
-----------------------------------
- Admin (`/v1/admin/*`): tenant management, key rotation, health cards, usage exports
- Owner (`/v1/owner/*`): schedules, KPIs, callbacks, conversations, exports, lockdown
- CRM (`/v1/crm/*`): customers, appointments, conversations
- Widget (`/v1/widget/*`): widget bootstrap and public chat flows
- Chat (`/v1/chat/*`): chat APIs (non-widget)
- Twilio/Telephony (`/twilio/*`, `/v1/twilio/*`, `/telephony/*`, `/v1/telephony/*`): webhooks and voice session flows
- Billing (`/v1/billing/*`): Stripe webhook and subscription flows
- Integrations (`/v1/integrations/*`): calendar/email/QBO OAuth and sync

Versioning
----------
Most APIs are under `/v1/*`. Prefer adding new functionality under versioned routes.

