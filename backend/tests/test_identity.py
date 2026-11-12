from nexus.identity import hash_password, verify_password, token_digest
import pytest


def test_scrypt_password_roundtrip():
    encoded = hash_password("correct-horse-long-password")
    assert encoded.startswith("scrypt$")
    assert verify_password("correct-horse-long-password", encoded)
    assert not verify_password("incorrect-password", encoded)


def test_scrypt_unique_salt():
    assert hash_password("correct-horse-long-password") != hash_password("correct-horse-long-password")


def test_short_password_rejected():
    with pytest.raises(ValueError):
        hash_password("too-short")


def test_invalid_hash_rejected():
    assert not verify_password("any password", "invalid")
    assert token_digest("secret") != "secret"


def test_change_password_requires_auth():
    from fastapi.testclient import TestClient
    from nexus.main import app
    client = TestClient(app)
    response = client.post("/api/auth/change-password", json={
        "current_password": "old-secret",
        "new_password": "a-new-long-password-123456",
    })
    assert response.status_code == 401


def test_change_password_rejects_short_password():
    from fastapi.testclient import TestClient
    from nexus.main import app
    client = TestClient(app)
    response = client.post("/api/auth/change-password", json={
        "current_password": "old-secret",
        "new_password": "short",
    })
    assert response.status_code == 422
