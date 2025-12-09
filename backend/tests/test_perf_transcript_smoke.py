import time

from app.repositories import conversations_repo


def test_long_transcript_storage_perf():
    """Ensure storing and reading long transcripts stays performant."""
    conv = conversations_repo.create(channel="owner_chat", business_id="default_business")
    long_line = "lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 5
    # Append ~500 messages (250 user + 250 assistant).
    for _ in range(250):
        conversations_repo.append_message(conv.id, role="user", text=long_line)
        conversations_repo.append_message(conv.id, role="assistant", text=long_line[::-1])

    start = time.perf_counter()
    loaded = conversations_repo.get(conv.id)
    elapsed = time.perf_counter() - start
    assert loaded is not None
    assert len(loaded.messages) == 500
    # Retrieval should remain under a reasonable bound even with many messages.
    assert elapsed < 0.5
