Statement of Applicability (Draft)
==================================

Purpose
-------
Map ISO 27001 Annex A controls to the current state (Implemented / Planned / Not Applicable) with references to evidence.

Key controls
------------
- **A.5 Information security policies** - Implemented. Policies documented in `ISMS_SCOPE.md`, `ACCESS_CONTROL_POLICY.md`, `SECURE_SDLC.md`.
- **A.6 Organization of information security** - Implemented. Roles defined in `INCIDENT_RESPONSE_PLAN.md` and `AUDIT_AND_MANAGEMENT_REVIEW.md`.
- **A.8 Asset management** - Implemented. Assets and boundaries in `ISMS_SCOPE.md`; vendor assets tracked in `VENDOR_REGISTER.md`.
- **A.9 Access control** - Implemented/Planned. SSO/MFA and access reviews in `ACCESS_CONTROL_POLICY.md`; GitHub branch protections in place; CI secrets restricted.
- **A.10 Cryptography** - Implemented. TLS enforced via Cloud Run; secret storage in Secret Manager; token rotation tracked in #84.
- **A.12 Operations security** - Implemented. Logging/monitoring (`LOGGING_AND_ALERTS.md`), malware protection via dependency scanning, change control via PR reviews and CI gates.
- **A.13 Communications security** - Implemented. Webhook/Twilio signature verification (#88), HTTPS only, CSP documented in `WIKI.md`.
- **A.14 System acquisition, development and maintenance** - Implemented. Secure SDLC in `SECURE_SDLC.md`; SAST/DAST/coverage gates in CI.
- **A.15 Supplier relationships** - Implemented/Planned. Vendor register with DPAs in `VENDOR_REGISTER.md`; review cadence noted.
- **A.16 Incident management** - Implemented. `INCIDENT_RESPONSE_PLAN.md`.
- **A.17 Information security aspects of business continuity** - Implemented/Planned. DR/BCP and backup testing in `DR_BCP.md` and `BACKUP_AND_RESTORE.md`.
- **A.18 Compliance** - Implemented/Planned. Data handling mapped in `PRIVACY_POLICY.md` and `TERMS_OF_SERVICE.md`; internal audits scheduled in `AUDIT_AND_MANAGEMENT_REVIEW.md`.

Planned improvements
--------------------
- Artifact signing for build outputs (supply chain hardening).
- Formal evidence log for access reviews and backup/restore test runs (linked from respective docs).
- External ISO 27001 certification timeline and partner selection (tracked in `AUDIT_AND_MANAGEMENT_REVIEW.md`).
