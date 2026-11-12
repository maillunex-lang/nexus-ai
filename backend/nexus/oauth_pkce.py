"""Pure PKCE and redirect URI validators. No OAuth tokens issued yet."""
import base64
import hashlib
import hmac
import re
from urllib.parse import urlsplit

PKCE_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
CHALLENGE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def valid_pkce_verifier(verifier: str) -> bool:
    return bool(PKCE_PATTERN.fullmatch(verifier))


def pkce_s256(verifier: str) -> str:
    if not valid_pkce_verifier(verifier):
        raise ValueError("Invalid PKCE verifier")
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def verify_pkce(verifier: str, challenge: str) -> bool:
    return bool(CHALLENGE_PATTERN.fullmatch(challenge)) and valid_pkce_verifier(verifier) and hmac.compare_digest(pkce_s256(verifier), challenge)


def validate_redirect_uri(uri: str) -> bool:
    if len(uri) > 2048 or "#" in uri or "\\" in uri:
        return False
    try:
        parsed = urlsplit(uri)
        if parsed.username or parsed.password or not parsed.hostname:
            return False
        if parsed.scheme == "https":
            return True
        return parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")
    except ValueError:
        return False
