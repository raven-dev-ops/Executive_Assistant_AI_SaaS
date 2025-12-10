from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter()


def _planner_path() -> Path:
    """Locate PLANNER.md relative to this router."""
    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = ancestor / "PLANNER.md"
        if candidate.exists():
            return candidate
    # Fallback: assume repo root is two levels up.
    return current.parents[2] / "PLANNER.md"


PLANNER_PATH = _planner_path()


def _load_planner_html() -> str:
    try:
        return PLANNER_PATH.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(
            status_code=404, detail="Planner document not found or unreadable"
        )


@router.get("/planner", response_class=HTMLResponse, tags=["planner"])
async def planner_brief() -> HTMLResponse:
    """Serve the investor planner/brief as a static HTML page."""
    html = _load_planner_html()
    return HTMLResponse(content=html, media_type="text/html")
