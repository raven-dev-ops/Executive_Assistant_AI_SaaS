import httpx

from app.services import geo_utils, zip_enrichment


def test_derive_neighborhood_label_prefers_zip_code() -> None:
    assert geo_utils.derive_neighborhood_label("123 Main St, Anytown, 94107") == "94107"


def test_derive_neighborhood_label_uses_trailing_segment_when_no_zip() -> None:
    assert geo_utils.derive_neighborhood_label("456 Oak Ave, Springfield") == "Springfield"


def test_derive_neighborhood_label_falls_back_to_unspecified() -> None:
    assert geo_utils.derive_neighborhood_label("") == "unspecified"
    assert geo_utils.derive_neighborhood_label("No commas or zips here") == "unspecified"


def test_fetch_zip_income_rejects_invalid_or_short_zip() -> None:
    profile = zip_enrichment.fetch_zip_income("12")
    assert profile.zip_code == "12"
    assert profile.median_household_income is None
    assert profile.source == "none"
    assert profile.error == "Invalid or empty ZIP code"


def test_fetch_zip_income_parses_valid_response(monkeypatch) -> None:
    # Dummy HTTPX client returning a valid Census-style payload.
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[list[str]]:
            return [
                ["NAME", "B19013_001E", "state", "zip code tabulation area"],
                ["ZCTA5 94107", "75000", "06", "94107"],
            ]

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        def __enter__(self) -> "DummyClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

        def get(self, url, params=None):  # type: ignore[no-untyped-def]
            return DummyResponse()

    monkeypatch.setattr(httpx, "Client", DummyClient)

    profile = zip_enrichment.fetch_zip_income("94107")
    assert profile.zip_code == "94107"
    assert profile.median_household_income == 75000
    assert profile.source == "census_acs_2022"
    assert profile.error is None


def test_fetch_zip_income_handles_parse_errors(monkeypatch) -> None:
    # Dummy HTTPX client returning an unexpected payload shape to trigger parse_error.
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return ["not-a-table"]

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        def __enter__(self) -> "DummyClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

        def get(self, url, params=None):  # type: ignore[no-untyped-def]
            return DummyResponse()

    monkeypatch.setattr(httpx, "Client", DummyClient)

    profile = zip_enrichment.fetch_zip_income("94107")
    assert profile.zip_code == "94107"
    assert profile.median_household_income is None
    assert profile.source == "census_acs_2022"
    assert profile.error == "parse_error"
