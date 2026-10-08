import io

import pytest
from PIL import Image

from backend.errors import ApiError
from backend.services.validation import MAX_DIMENSION, sanitize_filename, validate_upload
from tests.conftest import make_png_bytes

LIMIT = 2 * 1024 * 1024


def _encode(fmt, mode="RGB", size=(64, 64)):
    buffer = io.BytesIO()
    Image.new(mode, size, 90).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.mark.parametrize("name,data", [
    ("scan.png", make_png_bytes()),
    ("scan.jpg", _encode("JPEG")),
    ("scan.JPEG", _encode("JPEG")),
    ("scan.bmp", _encode("BMP")),
])
def test_supported_formats_are_accepted(name, data):
    validated = validate_upload(name, data, LIMIT)
    assert validated.image.mode == "RGB"
    assert validated.source_format in {"PNG", "JPEG", "BMP"}
    assert len(validated.sha256) == 64


def test_unsupported_extension_is_rejected():
    with pytest.raises(ApiError) as info:
        validate_upload("scan.gif", _encode("PNG"), LIMIT)
    assert info.value.status == 415 and info.value.code == "UNSUPPORTED_FILE_TYPE"


def test_real_format_is_checked_not_only_extension():
    gif = io.BytesIO()
    Image.new("P", (64, 64)).save(gif, format="GIF")
    with pytest.raises(ApiError) as info:
        validate_upload("sneaky.png", gif.getvalue(), LIMIT)
    assert info.value.code == "UNSUPPORTED_FILE_TYPE"


def test_text_file_renamed_to_png_is_invalid_image():
    with pytest.raises(ApiError) as info:
        validate_upload("scan.png", b"hello world, not an image", LIMIT)
    assert info.value.status == 415 and info.value.code == "INVALID_IMAGE"


def test_empty_file_is_rejected():
    with pytest.raises(ApiError) as info:
        validate_upload("scan.png", b"", LIMIT)
    assert info.value.code == "EMPTY_FILE"


def test_oversized_file_is_rejected():
    with pytest.raises(ApiError) as info:
        validate_upload("scan.png", make_png_bytes(), 10)
    assert info.value.status == 413 and info.value.code == "FILE_TOO_LARGE"


def test_truncated_png_is_corrupt():
    data = make_png_bytes(size=(200, 200))[:-200]
    with pytest.raises(ApiError) as info:
        validate_upload("scan.png", data, LIMIT)
    assert info.value.code in {"CORRUPT_IMAGE", "INVALID_IMAGE"}


def test_tiny_image_is_out_of_range():
    with pytest.raises(ApiError) as info:
        validate_upload("scan.png", make_png_bytes(size=(8, 8)), LIMIT)
    assert info.value.status == 422 and info.value.code == "IMAGE_DIMENSIONS_OUT_OF_RANGE"


def test_huge_dimensions_are_out_of_range():
    buffer = io.BytesIO()
    Image.new("L", (MAX_DIMENSION + 1, 40)).save(buffer, format="PNG")
    with pytest.raises(ApiError) as info:
        validate_upload("wide.png", buffer.getvalue(), 50 * 1024 * 1024)
    assert info.value.code == "IMAGE_DIMENSIONS_OUT_OF_RANGE"


def test_sanitize_filename_strips_paths_and_controls():
    assert sanitize_filename("../../etc/passwd.png") == "passwd.png"
    assert sanitize_filename("C:\\users\\me\\scan.png") == "scan.png"
    assert sanitize_filename("bad\x00name.png") == "badname.png"
    assert sanitize_filename("") == "upload"
    assert len(sanitize_filename("a" * 500 + ".png")) <= 120
