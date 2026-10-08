"""Upload validation tests."""

from __future__ import annotations

import io

import pytest

from app.core.exceptions import FileTooLargeError, ImageValidationError, ValidationError
from app.services.validation import _safe_name, unique_upload_path, validate_upload


def post(client, filename, data, content_type="image/png", field="image"):
    """Upload helper — the 3-tuple sets the part's declared MIME type."""
    return client.post(
        "/api/predict",
        data={field: (io.BytesIO(data), filename, content_type)},
        content_type="multipart/form-data",
    )


def test_rejects_missing_file_field(client):
    response = client.post("/api/predict", data={}, content_type="multipart/form-data")
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "validation_error"
    assert "No file was uploaded" in body["error"]["message"]


def test_rejects_empty_file_field(client):
    response = client.post(
        "/api/predict",
        data={"image": (io.BytesIO(b""), "empty.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code in {400}
    assert response.get_json()["error"]["code"] == "validation_error"


def test_rejects_unsupported_extension(client, png_bytes):
    response = post(client, "scan.gif", png_bytes, content_type="image/gif")
    assert response.status_code == 422
    body = response.get_json()
    assert body["error"]["code"] == "unsupported_file_type"
    assert ".jpg" in body["error"]["details"]["allowed_extensions"]


def test_rejects_executable_renamed_to_png(client):
    response = post(client, "malware.png", b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00binary-payload")
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_image"


def test_rejects_html_uploaded_as_image(client):
    response = post(client, "page.jpg", b"<html><body>not an image</body></html>", content_type="image/jpeg")
    assert response.status_code == 422


def test_rejects_unsupported_content_type(client, png_bytes):
    response = post(client, "scan.png", png_bytes, content_type="application/pdf")
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "unsupported_content_type"


def test_accepts_alternative_field_name(client, png_bytes):
    response = post(client, "scan.png", png_bytes, field="file")
    assert response.status_code == 201


def test_accepts_all_supported_extensions(client, png_bytes):
    for extension in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
        response = post(client, f"scan{extension}", png_bytes, content_type="image/png")
        assert response.status_code == 201, extension


def test_rejects_oversized_upload(small_client, png_bytes):
    payload = png_bytes + b"\0" * (2 * 1024 * 1024)  # ~2 MB against a 1 MB limit
    response = post(small_client, "big.png", payload)
    assert response.status_code in {413}
    assert response.get_json()["error"]["code"] == "file_too_large"


def test_safe_name_strips_path_traversal():
    assert _safe_name("../../etc/passwd.png") == "passwd.png"
    assert _safe_name("..\\..\\windows\\system32.png").endswith(".png")
    assert _safe_name("????.jpg") == "upload.jpg"
    assert _safe_name("/absolute/path/scan.jpg") == "scan.jpg"
    assert chr(92) not in _safe_name("..\\..\\windows\\system32.png")


def test_unique_upload_path_never_collides(tmp_path):
    first = unique_upload_path(tmp_path, "scan.png", "abc")
    first.write_bytes(b"x")
    second = unique_upload_path(tmp_path, "scan.png", "abc")
    assert first != second
    assert not second.exists()


def test_validate_upload_returns_metadata(client, png_bytes):
    """Exercise the validator directly for the returned metadata."""
    with client.application.test_request_context(
        "/api/predict",
        method="POST",
        data={"image": (io.BytesIO(png_bytes), "Patient 01 MRI.PNG")},
        content_type="multipart/form-data",
    ):
        from flask import request

        upload = validate_upload(request, client.application.config["BTD_CONFIG"])
        assert upload.filename == "Patient 01 MRI.PNG"
        assert upload.safe_name == "Patient_01_MRI.png"
        assert upload.extension == ".png"
        assert upload.size == len(png_bytes)
        assert upload.size_mb > 0


def test_rejects_extremely_long_filename(client, png_bytes):
    response = post(client, f"{'a' * 300}.png", png_bytes)
    assert response.status_code == 400


@pytest.mark.parametrize("field", ["mri", "scan", "upload"])
def test_accepts_documented_field_aliases(client, png_bytes, field):
    response = post(client, "scan.png", png_bytes, field=field)
    assert response.status_code == 201
