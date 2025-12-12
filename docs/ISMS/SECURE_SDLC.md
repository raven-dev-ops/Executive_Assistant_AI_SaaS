Secure SDLC & CI/CD Controls
============================

Standards
---------
- **Source control**: All changes via PR with review; `main` is protected and requires passing CI.
- **Static analysis & quality gates**: Ruff, Black, mypy, Bandit, pytest with 85% coverage minimum, and CodeQL (SAST) run on push/PR.
- **Secrets & dependencies**: Gitleaks on push/PR; pip-audit on push/PR + weekly; dependency review on PRs; SBOM published as artifact.
- **Build integrity**: Reproducible installs via `pyproject.toml`; no storing secrets in repo; plan to add artifact signing (tracked).
- **Test strategy**: Unit/integration tests in `backend/tests`; smoke/perf suites in `.github/workflows/perf-smoke.yml`; new features require tests.

Change management
-----------------
- PR template requires risk/rollback notes.
- High-risk changes (telephony webhooks, auth, scheduling) need explicit reviewer with domain context.
- Hotfixes require post-merge retro issue and coverage follow-up.

Release and deployment
----------------------
- CI builds and uploads coverage; artifacts for coverage.xml and SBOM are kept 7-14 days.
- Production deploys go through GitHub Actions/Cloud Build with environment-specific secrets; manual approvals for prod.
- Post-deploy checks: monitor owner notifications, Twilio/webhook alert dashboards, and perf smoke workflow status.
