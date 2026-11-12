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
