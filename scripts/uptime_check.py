#!/usr/bin/env python
"""
Simple synthetic uptime check for core endpoints.

Usage:
  python scripts/uptime_check.py --base http://localhost:8000

Environment variables:
  OWNER_TOKEN: optional X-Owner-Token for widget/chat calls
  ADMIN_API_KEY: optional X-Admin-API-Key for admin paths
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import requests


def check(url: str, method: str = "GET", **kwargs) -> float:
    start = time.time()
    resp = requests.request(method, url, timeout=5, **kwargs)
    elapsed = (time.time() - start) * 1000.0
    if resp.status_code >= 400:
        raise RuntimeError(f"{url} returned {resp.status_code}: {resp.text[:200]}")
    return elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic uptime check")
    parser.add_argument("--base", default="http://localhost:8000", help="Backend base URL")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    owner_token = os.getenv("OWNER_TOKEN", "")
    admin_key = os.getenv("ADMIN_API_KEY", "")

    try:
        t1 = check(f"{base}/healthz")
        t2 = check(f"{base}/readyz")

        # Widget chat start (stub defaults OK).
        headers = {}
        if owner_token:
            headers["X-Owner-Token"] = owner_token
        t3 = check(f"{base}/v1/widget/start", method="POST", json={}, headers=headers)

        # Twilio SMS webhook (stub provider path).
        t4 = check(
            f"{base}/twilio/sms",
            method="POST",
            data={"From": "+15550000000", "Body": "uptime check"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        # Admin anomalies as a proxy for auth + DB.
        admin_headers = {"X-Admin-API-Key": admin_key} if admin_key else {}
        t5 = check(f"{base}/v1/admin/security/anomalies", headers=admin_headers)

        print("OK", f"healthz={t1:.0f}ms readyz={t2:.0f}ms widget={t3:.0f}ms twilio_sms={t4:.0f}ms admin_anomalies={t5:.0f}ms")
        return 0
    except Exception as exc:
        print("FAIL", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
