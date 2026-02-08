Developer Workflow
==================

This repo uses an issue-first workflow.

1. Create a GitHub issue for the change
---------------------------------------
See `AGENTS.md` for required labels and milestones.

2. Create a feature branch
--------------------------
Example: `issue-123-short-title`

3. Run checks locally
---------------------
Backend:
- `cd backend`
- `pip install -e .[dev]`
- `ruff check .`
- `black --check .`
- `mypy ...` (see CI for the exact module list)
- `pytest`

Frontend:
- `cd frontend`
- `npm ci`
- `npm run lint`
- `npm run build`

4. Open a PR (required)
-----------------------
Do not push directly to `main`. Open a PR and link the issue (use `Fixes #123`).

