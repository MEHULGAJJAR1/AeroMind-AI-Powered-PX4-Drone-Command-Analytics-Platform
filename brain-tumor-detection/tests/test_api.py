import io
import uuid

from tests.conftest import make_png_bytes


def _upload(client, data=None, name="scan.png"):
    payload = data if data is not None else make_png_bytes()
    return client.post(
        "/api/uploads",
        data={"file": (io.BytesIO(payload), name)},
        content_type="multipart/form-data",
    )


def _predict(client, upload_id):
    return client.post("/api/predictions", json={"upload_id": upload_id})


def test_health_reports_loaded_model(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["model_version"].startswith("BrainTumorCNN-64px-")


def test_model_metadata(client):
    body = client.get("/api/model").get_json()
    assert body["loaded"] is True
    assert body["classes"] == ["glioma", "meningioma", "no_tumor", "pituitary"]
    assert body["img_size"] == 64
    assert body["test_accuracy"] == 0.9


def test_full_upload_predict_history_flow(client):
    upload = _upload(client)
    assert upload.status_code == 201
    upload_body = upload.get_json()
    assert upload_body["width"] == 96 and upload_body["height"] == 96
    assert upload_body["disclaimer"]

    prediction = _predict(client, upload_body["upload_id"])
    assert prediction.status_code == 201
    result = prediction.get_json()
    assert result["predicted_class"] in {"glioma", "meningioma", "no_tumor", "pituitary"}
    assert 0 < result["confidence"] <= 1
    assert abs(sum(result["probabilities"].values()) - 1.0) < 1e-3
    assert result["tumor_detected"] == (result["predicted_class"] != "no_tumor")
    assert result["original_filename"] == "scan.png"
    assert result["thumbnail_url"].endswith("/thumbnail")

    thumb = client.get(result["thumbnail_url"])
    assert thumb.status_code == 200 and thumb.mimetype == "image/jpeg"

    listing = client.get("/api/predictions?limit=5").get_json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == result["id"]

    detail = client.get(f"/api/predictions/{result['id']}").get_json()
    assert detail["probabilities"] == result["probabilities"]

    # The upload is consumed after prediction.
    assert _predict(client, upload_body["upload_id"]).status_code == 404

    assert client.delete(f"/api/predictions/{result['id']}").status_code == 204
    assert client.get(f"/api/predictions/{result['id']}").status_code == 404
    assert client.get(f"/api/predictions/{result['id']}/thumbnail").status_code == 404


def test_clear_history(client):
    for _ in range(2):
        upload_id = _upload(client).get_json()["upload_id"]
        assert _predict(client, upload_id).status_code == 201
    assert client.get("/api/predictions").get_json()["total"] == 2
    assert client.delete("/api/predictions").get_json() == {"deleted": 2}
    assert client.get("/api/predictions").get_json()["total"] == 0


def test_pagination_bounds(client):
    assert client.get("/api/predictions?limit=0").status_code == 400
    assert client.get("/api/predictions?limit=abc").status_code == 400
    assert client.get("/api/predictions?offset=-1").status_code == 400
    assert client.get("/api/predictions?limit=100").status_code == 200


def test_unsupported_upload_returns_structured_error(client):
    response = _upload(client, data=b"GIF89a....", name="scan.gif")
    assert response.status_code == 415
    error = response.get_json()["error"]
    assert error["code"] == "UNSUPPORTED_FILE_TYPE"
    assert "message" in error


def test_missing_file_field(client):
    response = client.post("/api/uploads", data={}, content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MISSING_FILE"


def test_invalid_prediction_body(client):
    assert _predict(client, None).status_code == 400
    response = client.post("/api/predictions", data="not json", content_type="text/plain")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_REQUEST"


def test_path_traversal_upload_ids_are_rejected(client):
    for bad in ["../../etc/passwd", "not-a-hex-id", uuid.uuid4().hex.upper()]:
        response = _predict(client, bad)
        assert response.status_code == 404
        assert response.get_json()["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert client.get("/api/predictions/../../etc").status_code == 404
    assert client.get(f"/api/predictions/{'0' * 32}").status_code == 404


def test_unknown_api_route_returns_json(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.is_json
    assert response.get_json()["error"]["code"] == "NOT_FOUND"


def test_too_large_upload_returns_413_json(client):
    big = make_png_bytes(size=(1400, 1400), mode="RGB", seed=3)
    assert len(big) > 2 * 1024 * 1024
    response = _upload(client, data=big)
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "FILE_TOO_LARGE"


def test_predict_without_model_returns_503_but_upload_still_works(unloaded_app):
    client = unloaded_app.test_client()
    health = client.get("/api/health").get_json()
    assert health["model_loaded"] is False
    upload = _upload(client)
    assert upload.status_code == 201
    response = _predict(client, upload.get_json()["upload_id"])
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "MODEL_UNAVAILABLE"
    assert client.get("/api/model").get_json()["error"]


def test_security_headers_and_frontend_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Brain Tumor Detection" in response.data
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert client.get("/api/health").headers["Cache-Control"] == "no-store"
    assert client.get("/static/js/app.js").status_code == 200
