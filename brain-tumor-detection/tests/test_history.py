"""History store + rate limiter unit tests."""

from __future__ import annotations

from PIL import Image

from app.core.ratelimit import SlidingWindowRateLimiter
from app.services.history import HistoryStore, make_thumbnail_data_uri


def sample_record(**overrides):
    record = {
        "filename": "scan.png",
        "content_type": "image/png",
        "size_bytes": 2048,
        "width": 256,
        "height": 256,
        "prediction": "tumor",
        "is_tumor": True,
        "confidence": 0.91,
        "uncertain": False,
        "probabilities": {"no_tumor": 0.09, "tumor": 0.91},
        "latency_ms": 42.0,
        "model": {"name": "Test CNN", "device": "cpu"},
        "image_hash": "abc123",
        "notes": None,
        "thumbnail": None,
        "upload_path": None,
    }
    record.update(overrides)
    return record


def test_add_and_get(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    stored = store.add(sample_record())
    assert store.count() == 1

    fetched = store.get(stored.id)
    assert fetched is not None
    assert fetched.prediction == "tumor"
    assert fetched.is_tumor is True
    assert fetched.probabilities == {"no_tumor": 0.09, "tumor": 0.91}
    assert fetched.to_dict()["prediction"]["display_name"] == "Tumor detected"
    assert fetched.to_dict()["size_mb"] == 0.002


def test_get_missing_returns_none(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    assert store.get("nope") is None


def test_list_is_newest_first_and_paginates(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    for index in range(5):
        store.add(sample_record(filename=f"scan-{index}.png"))

    page = store.list(limit=2, offset=0)
    assert [record.filename for record in page] == ["scan-4.png", "scan-3.png"]
    assert len(store.list(limit=2, offset=4)) == 1
    assert store.list(limit=1000)[0].filename == "scan-4.png"  # limit clamped, still newest first


def test_delete_and_clear_remove_upload_files(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    upload = tmp_path / "uploads" / "a.png"
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(b"x")

    stored = store.add(sample_record(upload_path=str(upload)))
    assert store.delete(stored.id) is True
    assert store.count() == 0
    assert not upload.exists()
    assert store.delete(stored.id) is False

    store.add(sample_record())
    store.add(sample_record())
    assert store.clear() == 2
    assert store.count() == 0


def test_pruning_respects_max_rows(tmp_path):
    store = HistoryStore(tmp_path / "history.db", max_rows=3)
    for index in range(6):
        store.add(sample_record(filename=f"scan-{index}.png"))
    assert store.count() == 3
    assert [record.filename for record in store.list(limit=10)] == [
        "scan-5.png",
        "scan-4.png",
        "scan-3.png",
    ]


def test_stats(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    store.add(sample_record(confidence=0.9, is_tumor=True, prediction="tumor", latency_ms=10))
    store.add(sample_record(confidence=0.7, is_tumor=False, prediction="no_tumor", latency_ms=20))

    stats = store.stats()
    assert stats["total"] == 2
    assert stats["tumor_detected"] == 1
    assert stats["no_tumor"] == 1
    assert stats["tumor_rate"] == 0.5
    assert stats["average_confidence"] == 0.8
    assert stats["average_latency_ms"] == 15.0
    assert stats["by_label"] == {"tumor": 1, "no_tumor": 1}
    assert stats["last_prediction_at"]


def test_stats_on_empty_store(tmp_path):
    stats = HistoryStore(tmp_path / "history.db").stats()
    assert stats["total"] == 0
    assert stats["average_confidence"] is None
    assert stats["by_label"] == {}


def test_corrupt_probabilities_json_is_tolerated(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    stored = store.add(sample_record())
    with store._connect() as connection:  # noqa: SLF001 - intentional white-box test
        connection.execute("UPDATE predictions SET probabilities = 'not json' WHERE id = ?", (stored.id,))
    assert store.get(stored.id).probabilities == {}


def test_thumbnail_generation():
    image = Image.new("RGB", (400, 300), "white")
    uri = make_thumbnail_data_uri(image)
    assert uri.startswith("data:image/jpeg;base64,")
    assert len(uri) < 20_000


# --------------------------------------------------------------------------- #
# Rate limiter
# --------------------------------------------------------------------------- #
def test_limiter_allows_up_to_the_limit():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    results = [limiter.consume("client", now=1000 + i) for i in range(3)]
    assert all(result.allowed for result in results)
    assert [result.remaining for result in results] == [2, 1, 0]

    blocked = limiter.consume("client", now=1003)
    assert blocked.allowed is False
    assert blocked.retry_after > 0


def test_limiter_window_slides():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10)
    limiter.consume("client", now=100)
    limiter.consume("client", now=101)
    assert limiter.consume("client", now=102).allowed is False
    assert limiter.consume("client", now=112).allowed is True  # first request expired


def test_limiter_is_per_key():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    assert limiter.consume("a", now=100).allowed
    assert limiter.consume("a", now=101).allowed is False
    assert limiter.consume("b", now=102).allowed


def test_limiter_disabled_when_limit_is_zero():
    limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60)
    assert limiter.enabled is False
    for index in range(10):
        result = limiter.consume("client", now=100 + index)
        assert result.allowed
        assert result.remaining == -1


def test_prune_drops_empty_buckets():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10)
    limiter.consume("client", now=100)
    limiter.prune(now=200)
    assert limiter.consume("client", now=201).remaining == 1
