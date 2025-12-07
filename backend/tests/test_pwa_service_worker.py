from pathlib import Path


def test_service_worker_defines_background_sync_queue():
    root = Path(__file__).resolve().parents[2]
    sw_path = root / "chat" / "sw.js"
    assert sw_path.exists()

    text = sw_path.read_text(encoding="utf-8")
    assert 'self.addEventListener("sync"' in text
    assert "chat-sync" in text
    assert "queue-chat" in text
    assert "flushQueue" in text
    assert "indexedDB" in text
