Access Control Policy (SSO/MFA, Joiner/Leaver)
===============================================

Principles
----------
- Least privilege for GitHub, CI, and cloud accounts.
- Strong authentication: SSO with MFA required for all human users; no shared accounts.
- Service accounts restricted to CI runners and Cloud Run with scoped roles.

Controls
--------
- **GitHub**: Enforce SSO + MFA, branch protection on `main`, required reviews + status checks (CI, gitleaks, pip-audit, CodeQL). Access review monthly; revoke stale collaborators.
- **CI secrets**: Stored in GitHub Actions secrets; limit write access to release managers. No plaintext secrets in repo (enforced by gitleaks).
- **Cloud**: IAM via Google Workspace/Cloud IAM groups; minimum roles for Cloud Run, Cloud SQL, GCS. Service accounts rotated quarterly; disable unused keys.
- **Joiner/Mover/Leaver**:
  - Joiner: manager approval, add to GitHub org with SSO/MFA, grant least-privileged roles in Google Cloud/IAM; document in access log.
  - Mover: adjust roles when responsibilities change; review API keys/service accounts owned.
  - Leaver: same-day access removal from GitHub, CI secrets, Cloud IAM; rotate shared tokens and Twilio/Stripe webhook secrets if applicable.
- **Periodic reviews**: Monthly access review for GitHub org, CI secrets, and Cloud IAM; track evidence in the access log (link tickets in GitHub).

Evidence to collect
-------------------
- GitHub org audit export (monthly).
- Cloud IAM role export (monthly) with diffs.
- CI secret inventory and rotation log (quarterly).
- MFA/SSO enforcement screenshots.
