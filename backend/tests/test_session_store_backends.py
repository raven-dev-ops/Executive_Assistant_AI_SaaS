from app.services import sessions


class _DummySettings:
    def __init__(self, session_store_backend: str) -> None:
        self.session_store_backend = session_store_backend


def test_session_store_defaults_to_inmemory_when_configured_as_memory(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sessions,
        "get_settings",
        lambda: _DummySettings(session_store_backend="memory"),
    )
    monkeypatch.delenv("REDIS_URL", raising=False)

    store = sessions._create_session_store()
    assert isinstance(store, sessions.InMemorySessionStore)


def test_session_store_falls_back_when_redis_library_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        sessions,
        "get_settings",
        lambda: _DummySettings(session_store_backend="redis"),
    )
    monkeypatch.setattr(sessions, "redis", None)

    store = sessions._create_session_store()
    assert isinstance(store, sessions.InMemorySessionStore)


def test_session_store_falls_back_when_redis_init_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        sessions,
        "get_settings",
        lambda: _DummySettings(session_store_backend="redis"),
    )

    class FailingRedisModule:
        def from_url(self, url: str):
            raise RuntimeError("redis down")

    monkeypatch.setattr(sessions, "redis", FailingRedisModule())

    store = sessions._create_session_store()
    assert isinstance(store, sessions.InMemorySessionStore)


def test_session_store_uses_redis_when_available(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        sessions,
        "get_settings",
        lambda: _DummySettings(session_store_backend="redis"),
    )

    class DummyRedisClient:
        def __init__(self) -> None:
            self._data: dict[str, str] = {}

        def setex(self, key: str, ttl: int, value: str) -> None:
            self._data[key] = value

        def get(self, key: str) -> str | None:
            return self._data.get(key)

    class DummyRedisModule:
        def __init__(self) -> None:
            self.last_url: str | None = None

        def from_url(self, url: str) -> DummyRedisClient:
            self.last_url = url
            return DummyRedisClient()

    dummy_module = DummyRedisModule()
    monkeypatch.setattr(sessions, "redis", dummy_module)
    monkeypatch.setenv("REDIS_URL", "redis://test-redis:6379/1")

    store = sessions._create_session_store()
    assert isinstance(store, sessions.RedisSessionStore)

    session = store.create(
        caller_phone="555-0100", business_id="b1", lead_source="test"
    )
    assert session.id
    fetched = store.get(session.id)
    assert fetched is not None
    assert fetched.caller_phone == "555-0100"

    store.end(session.id)
    ended = store.get(session.id)
    assert ended is not None
    assert ended.status == "COMPLETED"
    assert dummy_module.last_url == "redis://test-redis:6379/1"


def test_redis_session_store_save_persists_mutations_across_instances() -> None:
    class DummyRedisClient:
        def __init__(self) -> None:
            self._data: dict[str, str] = {}

        def setex(self, key: str, ttl: int, value: str) -> None:
            self._data[key] = value

        def get(self, key: str) -> str | None:
            return self._data.get(key)

    client = DummyRedisClient()
    store_a = sessions.RedisSessionStore(client, key_prefix="call", ttl_seconds=60)
    store_b = sessions.RedisSessionStore(client, key_prefix="call", ttl_seconds=60)

    session = store_a.create(
        caller_phone="555-0111", business_id="b2", lead_source="test"
    )
    session.stage = "ASK_PROBLEM"
    session.no_input_count = 2
    session.intent = "schedule_service"
    session.intent_confidence = 0.92
    session.is_emergency = True
    session.emergency_confidence = 0.88
    session.emergency_reasons = ["intent:emergency", "keyword:gas leak"]
    session.emergency_confirmation_pending = True
    store_a.save(session)

    fetched = store_b.get(session.id)
    assert fetched is not None
    assert fetched.caller_phone == "555-0111"
    assert fetched.business_id == "b2"
    assert fetched.lead_source == "test"
    assert fetched.stage == "ASK_PROBLEM"
    assert fetched.no_input_count == 2
    assert fetched.intent == "schedule_service"
    assert fetched.intent_confidence == 0.92
    assert fetched.is_emergency is True
    assert fetched.emergency_confidence == 0.88
    assert fetched.emergency_reasons == ["intent:emergency", "keyword:gas leak"]
    assert fetched.emergency_confirmation_pending is True


def test_session_store_prefers_redis_when_url_present(monkeypatch) -> None:
    monkeypatch.setattr(
        sessions,
        "get_settings",
        # Simulate default "memory" setting, but REDIS_URL provided.
        lambda: _DummySettings(session_store_backend="memory"),
    )

    class DummyRedisClient:
        def __init__(self) -> None:
            self._data: dict[str, str] = {}

        def setex(self, key: str, ttl: int, value: str) -> None:
            self._data[key] = value

        def get(self, key: str) -> str | None:
            return self._data.get(key)

    class DummyRedisModule:
        def from_url(self, url: str) -> DummyRedisClient:
            return DummyRedisClient()

    monkeypatch.setattr(sessions, "redis", DummyRedisModule())
    monkeypatch.setenv("REDIS_URL", "redis://auto:6379/0")

    store = sessions._create_session_store()
    assert isinstance(store, sessions.RedisSessionStore)


def test_parse_iso_datetime_handles_invalid_strings() -> None:
    assert sessions._parse_iso_datetime("") is None
    assert sessions._parse_iso_datetime("not-a-date") is None
    iso = "2024-01-01T12:00:00+00:00"
    parsed = sessions._parse_iso_datetime(iso)
    assert parsed is not None and parsed.year == 2024


def test_session_store_handles_corrupt_payload_and_missing(monkeypatch) -> None:
    class CorruptClient:
        def __init__(self) -> None:
            self._data: dict[str, str] = {}

        def get(self, key: str):
            return self._data.get(key)

        def setex(self, key: str, ttl: int, value: str) -> None:
            self._data[key] = value

    client = CorruptClient()
    store = sessions.RedisSessionStore(client, key_prefix="call", ttl_seconds=60)

    # Missing session id returns None.
    assert store.get("missing") is None

    # Corrupt JSON should also return None rather than raising.
    client.setex("call:bad", 60, "not-json")
    assert store.get("bad") is None

    # end() should no-op gracefully when session is missing.
    store.end("missing")
