from app.core.config import Settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hashing_and_verification():
    hashed = hash_password("correct-horse-battery")
    assert hashed != "correct-horse-battery"
    assert verify_password("correct-horse-battery", hashed)
    assert not verify_password("incorrect-password", hashed)


def test_access_token_round_trip_and_expiry_validation():
    settings = Settings(app_env="test", secret_key="test-signing-key-that-is-long-enough-for-tests")
    token, expires_at = create_access_token("user-123", "operator", settings)
    payload = decode_access_token(token, settings)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert expires_at.tzinfo is not None
    assert decode_access_token("not-a-token", settings) is None
