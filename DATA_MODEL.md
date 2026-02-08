Data Model (High Level)
=======================

The system is multi-tenant. Most entities are scoped to a `business_id`.

Core Entities
-------------
- Business (tenant)
  - Configuration: business hours, time zone, emergency rules, integration state, lockdown mode
- Customer
  - Identity and contact info (phone/email/address), notes, lead source
- Appointment
  - Scheduled time window (stored in UTC), service type, emergency flag, status, external ids
- Conversation
  - Channel (voice/web/SMS), timestamps, summary, optional transcript fields, outcome tags
- User
  - Owner/staff identity and roles, auth state, business membership

Operational/Supporting Entities
-------------------------------
- Audit events / security events
- Billing/subscription records (Stripe)
- OAuth tokens/state for integrations (Google Calendar, Gmail, QuickBooks)

Where To Look In Code
---------------------
- DB models: `backend/app/db_models.py`
- Repositories: `backend/app/repositories.py`
- Migrations: `backend/alembic/`

