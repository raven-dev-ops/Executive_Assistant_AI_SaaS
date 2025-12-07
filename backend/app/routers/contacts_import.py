from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import List, Optional, Tuple
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..deps import ensure_business_active, require_owner_dashboard_auth
from ..repositories import customers_repo
from ..metrics import metrics


router = APIRouter(dependencies=[Depends(require_owner_dashboard_auth)])
logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    imported: int
    skipped: int
    errors: List[str]


class ContactImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: List[str]


def _normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return digits


def _parse_csv_bytes(data: bytes) -> List[dict]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # Fallback for files saved with BOM or slight encoding drift.
        text = data.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader]


def _validate_row(
    row: dict,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], List[str]]:
    errors: List[str] = []
    name = (row.get("Name") or row.get("name") or "").strip()
    phone = _normalize_phone(row.get("Phone") or row.get("phone") or "")
    email = (row.get("Email") or row.get("email") or "").strip() or None
    address = (row.get("Address") or row.get("address") or "").strip() or None

    if not name:
        errors.append("missing name")
    if not phone:
        errors.append("missing phone")
    return (name or None, phone or None, email, address, errors)


def _import_rows(rows: List[dict], business_id: str) -> ImportResult:
    imported = 0
    skipped = 0
    errors: List[str] = []

    seen_phones: set[str] = set()

    for idx, row in enumerate(rows, start=1):
        name, phone, email, address, row_errors = _validate_row(row)
        if row_errors:
            skipped += 1
            errors.append(f"Row {idx}: " + "; ".join(row_errors))
            continue
        if phone in seen_phones:
            skipped += 1
            continue
        seen_phones.add(phone)

        existing = customers_repo.get_by_phone(phone, business_id=business_id)
        if existing:
            customers_repo.upsert(
                name=name or existing.name,
                phone=phone,
                email=email or existing.email,
                address=address or existing.address,
                business_id=business_id,
            )
            skipped += 1
            continue

        customers_repo.upsert(
            name=name or "Customer",
            phone=phone,
            email=email,
            address=address,
            business_id=business_id,
        )
        imported += 1

    return ImportResult(imported=imported, skipped=skipped, errors=errors)


@router.post("/import", response_model=ContactImportResponse)
async def import_contacts(
    file: UploadFile = File(..., description="CSV file with columns: Name, Phone, Email, Address"),
    business_id: str = Depends(ensure_business_active),
) -> ContactImportResponse:
    """Import contacts from a CSV file into the current tenant.

    This is a synchronous, bounded implementation that processes the CSV
    immediately. Large files should be chunked upstream; the intent is to
    cover the common case of small owner-managed contact lists.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="A CSV file is required.")

    content = await file.read()
    rows = _parse_csv_bytes(content)
    if not rows:
        raise HTTPException(status_code=400, detail="No rows detected in CSV.")

    try:
        result = _import_rows(rows, business_id)
    except Exception as exc:
        metrics.background_job_errors += 1
        logger.exception(
            "contacts_import_failed",
            extra={"business_id": business_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Import failed unexpectedly.")

    metrics.contacts_imported += result.imported
    if result.errors:
        metrics.contacts_import_errors += len(result.errors)
        logger.warning(
            "contacts_import_completed_with_errors",
            extra={
                "business_id": business_id,
                "imported": result.imported,
                "skipped": result.skipped,
                "errors": len(result.errors),
            },
        )
    else:
        logger.info(
            "contacts_import_completed",
            extra={
                "business_id": business_id,
                "imported": result.imported,
                "skipped": result.skipped,
            },
        )
    return ContactImportResponse(
        imported=result.imported,
        skipped=result.skipped,
        errors=result.errors,
    )
