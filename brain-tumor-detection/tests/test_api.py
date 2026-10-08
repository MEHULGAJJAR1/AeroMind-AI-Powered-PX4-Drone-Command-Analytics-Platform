"""End-to-end API tests (Flask test client → real model inference)."""

from __future__ import annotations

import io


def post_image(client, raw, filename="scan.png", content_type="image/png", extra=None):
    data = {"image": (io.BytesIO(raw), filename)}
    if extra:
        data.update(extra)
    return client.post("/api/predict", data=data, content_type="multipart/form-data")


# --------------------------------------------------------------------------- #
# Health & model
# --------------------------------------------------------------------------- #
def test_health_reports_ready_model(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "healthy"
    assert data["model_available"] is True
    assert data["model"]["device"] in {"cpu", "cuda", "mps"}
    assert data["model"]["model"]["class_labels"] == ["no_tumor", "tumor"]
    assert data["config"]["max_upload_mb"] >= 1


def test_health_reports_degraded_without_model(no_model_client):
    response = no_model_client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "degraded"
    assert data["model_available"] is False
    assert "No model checkpoint found" in data["model"]["error"]


def test_predict_without_model_returns_503_with_hint(no_model_client, png_bytes):
    response = post_image(no_model_client, png_bytes)
    assert response.status_code == 503
    body = response.get_json()
    assert body["error"]["code"] == "model_unavailable"
    assert "training.train" in body["error"]["message"]


def test_model_endpoint_returns_metadata(client):
    response = client.get("/api/model")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["architecture"] == "cnn"
    assert data["input"]["size"] > 0
    assert data["metrics"]["val_accuracy"] > 0
    assert data["loaded"] is True


def test_model_endpoint_503_without_model(no_model_client):
    assert no_model_client.get("/api/model").status_code == 503


# --------------------------------------------------------------------------- #
# Prediction
# --------------------------------------------------------------------------- #
def test_predict_returns_full_payload(client, png_bytes):
    response = post_image(client, png_bytes)
    assert response.status_code == 201
    data = response.get_json()["data"]

    prediction = data["prediction"]
    assert prediction["label"] in {"no_tumor", "tumor"}
    assert 0.0 <= prediction["confidence"] <= 1.0
    assert set(prediction["probabilities"]) == {"no_tumor", "tumor"}
    assert abs(sum(prediction["probabilities"].values()) - 1.0) < 1e-4
    assert prediction["is_tumor"] == (prediction["label"] == "tumor")
    assert isinstance(prediction["uncertain"], bool)
    assert prediction["recommendation"]

    assert data["model"]["device"] in {"cpu", "cuda", "mps"}
    assert data["timing"]["total_ms"] >= 0
    assert data["timing"]["inference_ms"] >= 0
    assert data["preprocess"]["input_size"]["width"] > 0
    assert data["image"]["filename"] == "scan.png"
    assert data["image"]["size_bytes"] == len(png_bytes)
    assert len(data["image"]["sha256"]) == 64
    assert data["history_id"]
    assert data["preprocessed_image"].startswith("data:image/png;base64,")


def test_predict_can_skip_preprocessed_preview(client, png_bytes):
    response = post_image(client, png_bytes, extra={"include_preprocessed": "0"})
    assert response.status_code == 201
    assert "preprocessed_image" not in response.get_json()["data"]


def test_predict_can_skip_history(client, png_bytes):
    before = client.get("/api/predictions").get_json()["data"]["total"]
    response = post_image(client, png_bytes, extra={"save_history": "0"})
    assert response.status_code == 201
    assert "history_id" not in response.get_json()["data"]
    after = client.get("/api/predictions").get_json()["data"]["total"]
    assert before == after


def test_predict_stores_notes(client, png_bytes):
    response = post_image(client, png_bytes, extra={"notes": "Patient follow-up 2026-03"})
    assert response.status_code == 201
    record_id = response.get_json()["data"]["history_id"]
    record = client.get(f"/api/predictions/{record_id}").get_json()["data"]
    assert record["notes"] == "Patient follow-up 2026-03"


def test_predict_is_deterministic_for_identical_input(client, png_bytes):
    first = post_image(client, png_bytes).get_json()["data"]["prediction"]
    second = post_image(client, png_bytes).get_json()["data"]["prediction"]
    assert first["confidence"] == second["confidence"]
    assert first["probabilities"] == second["probabilities"]


def test_predict_handles_grayscale_and_jpeg(client, jpeg_bytes):
    response = post_image(client, jpeg_bytes, filename="scan.jpg", content_type="image/jpeg")
    assert response.status_code == 201


def test_request_id_header_is_present(client):
    response = client.get("/api/health")
    assert response.headers.get("X-Request-Id")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
def test_history_records_predictions_and_paginates(client, png_bytes, jpeg_bytes):
    for index in range(5):
        assert post_image(client, png_bytes, filename=f"scan-{index}.png").status_code == 201

    listing = client.get("/api/predictions?limit=2&offset=0").get_json()["data"]
    assert listing["total"] == 5
    assert len(listing["items"]) == 2
    assert listing["has_more"] is True
    assert listing["items"][0]["thumbnail"].startswith("data:image/jpeg;base64,")

    page_two = client.get("/api/predictions?limit=2&offset=2").get_json()["data"]
    assert [item["id"] for item in page_two["items"]] != [item["id"] for item in listing["items"]]

    newest_first = client.get("/api/predictions?limit=5").get_json()["data"]["items"]
    timestamps = [item["created_ts"] for item in newest_first]
    assert timestamps == sorted(timestamps, reverse=True)


def test_history_single_delete(client, png_bytes):
    record_id = post_image(client, png_bytes).get_json()["data"]["history_id"]
    assert client.get(f"/api/predictions/{record_id}").status_code == 200

    deleted = client.delete(f"/api/predictions/{record_id}")
    assert deleted.status_code == 200
    assert deleted.get_json()["data"]["deleted"] == record_id
    assert client.get(f"/api/predictions/{record_id}").status_code == 404
    assert client.delete(f"/api/predictions/{record_id}").status_code == 404


def test_history_clear(client, png_bytes):
    post_image(client, png_bytes)
    post_image(client, png_bytes)
    assert client.get("/api/predictions").get_json()["data"]["total"] == 2

    cleared = client.delete("/api/predictions")
    assert cleared.status_code == 200
    assert cleared.get_json()["data"]["deleted"] == 2
    assert client.get("/api/predictions").get_json()["data"]["total"] == 0


def test_history_can_omit_thumbnails(client, png_bytes):
    post_image(client, png_bytes)
    items = client.get("/api/predictions?thumbnails=0").get_json()["data"]["items"]
    assert items[0]["thumbnail"] is None


def test_stats_aggregate(client, png_bytes):
    post_image(client, png_bytes)
    stats = client.get("/api/stats").get_json()["data"]
    assert stats["total"] == 1
    assert stats["tumor_detected"] + stats["no_tumor"] == 1
    assert 0.0 <= stats["tumor_rate"] <= 1.0
    assert stats["average_confidence"] is not None
    assert stats["model"]["available"] is True


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
def test_unknown_api_route_returns_json_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_unknown_page_returns_html_404(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert b"404" in response.data


def test_method_not_allowed_is_json(client):
    response = client.get("/api/predict")
    assert response.status_code == 405
    assert response.get_json()["error"]["code"] == "method_not_allowed"


def test_invalid_pagination_argument(client):
    response = client.get("/api/predictions?limit=abc")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_index_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"BrainScan" in response.data
    assert b"dropzone" in response.data
    assert b"btd-config" in response.data


def test_oversized_request_body_is_rejected_as_413(small_client, png_bytes):
    payload = png_bytes + b"\0" * (4 * 1024 * 1024)  # over the 3 MB content-length cap
    response = small_client.post(
        "/api/predict",
        data={"image": (io.BytesIO(payload), "huge.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "file_too_large"


# --------------------------------------------------------------------------- #
# Rate limiting & model reload
# --------------------------------------------------------------------------- #
def test_rate_limit_blocks_excess_posts(tmp_path, checkpoint_dir, png_bytes):
    import dataclasses

    from app.config import Config
    from app.factory import create_app

    config = dataclasses.replace(
        Config.for_testing(tmp_path), model_dir=checkpoint_dir, rate_limit=2, rate_window_seconds=60
    )
    limited = create_app(config).test_client()

    assert post_image(limited, png_bytes).status_code == 201
    assert post_image(limited, png_bytes).status_code == 201

    blocked = post_image(limited, png_bytes)
    assert blocked.status_code == 429
    assert blocked.get_json()["error"]["code"] == "rate_limited"
    assert blocked.headers["Retry-After"].isdigit()
    assert blocked.headers["X-RateLimit-Limit"] == "2"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"

    # Read-only endpoints stay available.
    assert limited.get("/api/health").status_code == 200


def test_model_reload_endpoint(client):
    response = client.post("/api/model/reload")
    assert response.status_code == 200
    assert response.get_json()["data"]["reloaded"] is True
