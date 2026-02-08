from app.services.privacy import mask_value, redact_iter, redact_text


def test_mask_value_masks_short_and_long_values():
    masked_short = mask_value("a")
    assert masked_short != "a"
    assert len(masked_short) == 1

    masked = mask_value("abcd")
    assert masked.endswith("cd")
    assert len(masked) == 4

    masked_ws = mask_value("  ab  ")
    assert len(masked_ws) == 2


def test_redact_text_returns_empty_input_unchanged():
    assert redact_text("") == ""


def test_redact_iter_skips_none_and_redacts_pii():
    out = redact_iter(["Email me at test@example.com", None, "no pii"])
    assert out == [redact_text("Email me at test@example.com"), "no pii"]
    assert "@" not in out[0]
    assert out[0].endswith("om")

