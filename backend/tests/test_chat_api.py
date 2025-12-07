from fastapi.testclient import TestClient

from app.main import app
from app.repositories import conversations_repo


client = TestClient(app)


def test_chat_endpoint_returns_reply_and_logs_conversation():
    # Clear any in-memory conversations to ensure a clean test.
    if hasattr(conversations_repo, "_by_id"):
        conversations_repo._by_id.clear()  # type: ignore[attr-defined]
        conversations_repo._by_business.clear()  # type: ignore[attr-defined]

    resp = client.post("/v1/chat", json={"text": "Hello, can you summarize my schedule?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply_text"]
    assert data["conversation_id"]

    conv = conversations_repo.get(data["conversation_id"])
    assert conv is not None
    assert len(conv.messages) >= 2
    assert conv.messages[0].role == "user"
