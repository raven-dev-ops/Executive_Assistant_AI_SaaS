import base64

from app.services.oauth_state import decode_state, encode_state


def test_oauth_state_roundtrip_basic() -> None:
    secret = "dev-secret"
    state = encode_state("biz-123", "gcalendar", secret)
    business_id, provider = decode_state(state, secret)
    assert business_id == "biz-123"
    assert provider == "gcalendar"


def test_oauth_state_roundtrip_handles_dot_byte_in_signature() -> None:
    secret = "dev-secret"
    found = False
    for i in range(1, 2000):
        business_id = f"biz-{i}"
        state = encode_state(business_id, "gmail", secret)
        payload_b64, sig_b64 = state.split(".", 1)
        sig_padded = sig_b64 + "=" * (-len(sig_b64) % 4)
        sig = base64.urlsafe_b64decode(sig_padded.encode())
        if b"." not in sig:
            continue
        decoded_business_id, decoded_provider = decode_state(state, secret)
        assert decoded_business_id == business_id
        assert decoded_provider == "gmail"
        found = True
        break
    assert found, "expected to find a signature containing '.' byte"


def test_oauth_state_rejects_invalid_format() -> None:
    try:
        decode_state("not-a-token", "secret")
        assert False, "decode_state should have raised"
    except ValueError as exc:
        assert str(exc) == "invalid_state_format"
