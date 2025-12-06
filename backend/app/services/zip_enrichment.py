from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import os

import httpx


logger = logging.getLogger(__name__)


@dataclass
class ZipIncomeProfile:
    zip_code: str
    median_household_income: int | None
    source: str
    fetched_at: datetime
    error: str | None = None


def fetch_zip_income(zip_code: str, timeout_seconds: float = 3.0) -> ZipIncomeProfile:
    """Fetch median household income for a US ZIP code using the Census API.

    This is a best-effort enrichment used for market analytics. When the API
    is unavailable or returns unexpected data, the function logs and returns
    a profile with `median_household_income=None`.
    """
    zip_code = (zip_code or "").strip()
    now = datetime.now(UTC)
    if not zip_code or len(zip_code) < 5:
        return ZipIncomeProfile(
            zip_code=zip_code,
            median_household_income=None,
            source="none",
            fetched_at=now,
            error="Invalid or empty ZIP code",
        )

    # Use ACS 5-year estimates; 2022 is a reasonable recent default.
    base_url = "https://api.census.gov/data/2022/acs/acs5"
    params = {
        "get": "NAME,B19013_001E",
        "for": f"zip code tabulation area:{zip_code}",
    }
    api_key = os.getenv("CENSUS_API_KEY")
    if api_key:
        params["key"] = api_key

    try:  # pragma: no cover - depends on external API
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.get(base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning(
            "zip_income_enrichment_failed",
            extra={"zip_code": zip_code, "error": str(exc)},
        )
        return ZipIncomeProfile(
            zip_code=zip_code,
            median_household_income=None,
            source="census_acs_2022",
            fetched_at=now,
            error=str(exc),
        )

    try:
        # Expect at least header + one data row.
        if not isinstance(data, list) or len(data) < 2:
            raise ValueError("Unexpected response shape")
        # Example: [["NAME","B19013_001E","state","zip code tabulation area"],
        #           ["ZCTA5 66202","60000","20","66202"]]
        row = data[1]
        median_raw = row[1]
        income = int(median_raw) if median_raw not in (None, "", "-666666666") else None
        return ZipIncomeProfile(
            zip_code=zip_code,
            median_household_income=income,
            source="census_acs_2022",
            fetched_at=now,
            error=None,
        )
    except Exception as exc:
        logger.warning(
            "zip_income_enrichment_parse_error",
            extra={"zip_code": zip_code, "error": str(exc), "raw": data},
        )
        return ZipIncomeProfile(
            zip_code=zip_code,
            median_household_income=None,
            source="census_acs_2022",
            fetched_at=now,
            error="parse_error",
        )
