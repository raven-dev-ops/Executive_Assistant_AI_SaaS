from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.services.feedback_store import FeedbackEntry, FeedbackStore


def test_feedback_store_appends_and_filters(tmp_path):
    path = tmp_path / "feedback.jsonl"
    store = FeedbackStore(path=str(path))

    now = datetime.now(UTC)
    store.append(
        FeedbackEntry(
            created_at=now - timedelta(minutes=10),
            business_id="b1",
            source="owner_dashboard",
            category="bug",
            summary="First",
            steps=None,
            expected=None,
            actual=None,
            call_sid="CA123",
            conversation_id="conv-1",
            session_id="sess-1",
            request_id="req-1",
            contact=None,
            url="https://example.com/a",
            user_agent="pytest",
        )
    )
    store.append(
        FeedbackEntry(
            created_at=now,
            business_id="b2",
            source="admin",
            category="idea",
            summary="Second",
            steps="Try this",
            expected="A",
            actual="B",
            call_sid=None,
            conversation_id=None,
            session_id=None,
            request_id=None,
            contact="test@example.com",
            url="https://example.com/b",
            user_agent="pytest",
        )
    )

    items = store.list(limit=10)
    assert [item["summary"] for item in items] == ["Second", "First"]

    assert len(store.list(business_id="b1")) == 1
    assert len(store.list(source="admin")) == 1
    assert len(store.list(category="bug")) == 1
    assert len(store.list(call_sid="CA123")) == 1
    assert len(store.list(conversation_id="conv-1")) == 1
    assert len(store.list(session_id="sess-1")) == 1
    assert len(store.list(request_id="req-1")) == 1
    assert len(store.list(since=now - timedelta(minutes=1))) == 1


def test_feedback_store_loads_existing_entries(tmp_path):
    path = tmp_path / "feedback.jsonl"
    now = datetime.now(UTC)
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "created_at": now.isoformat(),
                        "business_id": "b3",
                        "source": "widget",
                        "category": "support",
                        "summary": "Loaded",
                        "steps": None,
                        "expected": None,
                        "actual": None,
                        "call_sid": None,
                        "conversation_id": "conv-2",
                        "session_id": "sess-2",
                        "request_id": "req-2",
                        "contact": None,
                        "url": "https://example.com/c",
                        "user_agent": "pytest",
                    }
                ),
                "not json",
                json.dumps({"created_at": "not-a-date"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    store = FeedbackStore(path=str(path))
    items = store.list(limit=10)
    assert len(items) == 1
    assert items[0]["summary"] == "Loaded"
    assert items[0]["business_id"] == "b3"
