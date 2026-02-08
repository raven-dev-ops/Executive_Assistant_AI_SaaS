Engineering
===========

Primary references for engineering standards in this repo:
- `AGENTS.md`: required issue/PR workflow for improvements
- `CONTRIBUTING.md`: contributor expectations and local dev workflow
- `Project_Engineering_Whitepaper.pdf`: engineering culture, testing, and operational rigor

Quality Gates
-------------
- Backend CI runs lint/format/type checks and tests. See `.github/workflows/backend-ci.yml`.
- Prefer adding tests for behavior changes, especially in telephony, auth, and tenant isolation.

Release Hygiene
---------------
- Update `CHANGELOG.md` and `RELEASES.md` for user-visible changes.
- Bump versions for release-impacting changes (backend: `backend/pyproject.toml`).

