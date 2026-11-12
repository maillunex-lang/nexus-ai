from nexus.oauth_pkce import pkce_s256, verify_pkce, validate_redirect_uri
import pytest


def test_rfc7636_vector():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert pkce_s256(verifier) == challenge
    assert verify_pkce(verifier, challenge)
    assert not verify_pkce("a" * 43, challenge)


def test_short_pkce_rejected():
    with pytest.raises(ValueError):
        pkce_s256("short")


@pytest.mark.parametrize("uri,valid", [
    ("https://example.org/callback", True),
    ("http://localhost:4321/callback", True),
    ("http://127.0.0.1/callback", True),
    ("http://example.org/callback", False),
    ("https://user:password@example.org/callback", False),
    ("https://example.org/callback#fragment", False),
    ("javascript:alert(1)", False),
])
def test_redirect_uri(uri, valid):
    assert validate_redirect_uri(uri) is valid
