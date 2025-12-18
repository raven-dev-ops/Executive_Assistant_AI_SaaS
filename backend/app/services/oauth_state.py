from __future__ import annotations

import base64
import hmac
import json
import time
from hashlib import sha256
from typing import Tuple


def encode_state(business_id: str, provider: str, secret: str) -> str:
    payload = {"b": business_id, "p": provider, "ts": int(time.time())}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(secret.encode(), raw, sha256).digest()
    payload_b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{payload_b64}.{sig_b64}"


def decode_state(state: str, secret: str) -> Tuple[str, str]:
    try:
        payload_b64, sig_b64 = state.split(".", 1)
    except ValueError:
        raise ValueError("invalid_state_format")

    payload_padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    sig_padded = sig_b64 + "=" * (-len(sig_b64) % 4)
    payload_raw = base64.urlsafe_b64decode(payload_padded.encode())
    sig = base64.urlsafe_b64decode(sig_padded.encode())

    expected = hmac.new(secret.encode(), payload_raw, sha256).digest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("invalid_state_signature")
    payload = json.loads(payload_raw.decode())
    return payload.get("b"), payload.get("p")
