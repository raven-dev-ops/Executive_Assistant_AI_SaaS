from __future__ import annotations

import hmac
from hashlib import sha256
from types import SimpleNamespace

import pytest

from app.services import stripe_webhook


def _set_tolerance(monkeypatch, seconds: int) -> None:
    monkeypatch.setattr(
        stripe_webhook,
        "get_settings",
        lambda: SimpleNamespace(
            stripe=SimpleNamespace(replay_protection_seconds=seconds)
        ),
    )


def test_parse_signature_header_requires_fields() -> None:
    with pytest.raises(stripe_webhook.StripeSignatureError) as excinfo:
        stripe_webhook._parse_signature_header("t=123")
    assert str(excinfo.value) == "missing_fields"

    with pytest.raises(stripe_webhook.StripeSignatureError) as excinfo2:
        stripe_webhook._parse_signature_header("v1=abc")
    assert str(excinfo2.value) == "missing_fields"

    with pytest.raises(stripe_webhook.StripeSignatureError) as excinfo3:
        stripe_webhook._parse_signature_header("t=notint,v1=abc")
    assert str(excinfo3.value) == "missing_fields"


def test_verify_stripe_signature_accepts_valid_signature(monkeypatch) -> None:
    _set_tolerance(monkeypatch, 300)
    monkeypatch.setattr(stripe_webhook.time, "time", lambda: 1_000_000.0)

    ts = 1_000_000
    raw_body = b'{"id":"evt_1"}'
    secret = "whsec_test"
    signed_payload = f"{ts}.{raw_body.decode()}".encode()
    sig = hmac.new(secret.encode(), signed_payload, sha256).hexdigest()
    header = f"t={ts},v1={sig}"

    stripe_webhook.verify_stripe_signature(raw_body, header, secret)


def test_verify_stripe_signature_rejects_mismatch(monkeypatch) -> None:
    _set_tolerance(monkeypatch, 300)
    monkeypatch.setattr(stripe_webhook.time, "time", lambda: 1_000_000.0)

    ts = 1_000_000
    raw_body = b"{}"
    secret = "whsec_test"
    header = f"t={ts},v1=badsig"

    with pytest.raises(stripe_webhook.StripeSignatureError) as excinfo:
        stripe_webhook.verify_stripe_signature(raw_body, header, secret)
    assert str(excinfo.value) == "signature_mismatch"


def test_verify_stripe_signature_rejects_stale_timestamp(monkeypatch) -> None:
    _set_tolerance(monkeypatch, 60)
    monkeypatch.setattr(stripe_webhook.time, "time", lambda: 1_000_000.0)

    ts = 1_000_000 - 120
    raw_body = b"{}"
    secret = "whsec_test"
    signed_payload = f"{ts}.{raw_body.decode()}".encode()
    sig = hmac.new(secret.encode(), signed_payload, sha256).hexdigest()
    header = f"t={ts},v1={sig}"

    with pytest.raises(stripe_webhook.StripeReplayError) as excinfo:
        stripe_webhook.verify_stripe_signature(raw_body, header, secret)
    assert str(excinfo.value) == "timestamp_out_of_window"


def test_check_replay_blocks_duplicate_and_purges(monkeypatch) -> None:
    stripe_webhook._seen_events.clear()
    try:
        monkeypatch.setattr(stripe_webhook.time, "time", lambda: 1_000.0)
        stripe_webhook._seen_events["evt_old"] = 0.0

        stripe_webhook.check_replay("evt_new", window_seconds=10)
        assert "evt_old" not in stripe_webhook._seen_events

        with pytest.raises(stripe_webhook.StripeReplayError) as excinfo:
            stripe_webhook.check_replay("evt_new", window_seconds=10)
        assert str(excinfo.value) == "replayed_event"
    finally:
        stripe_webhook._seen_events.clear()
