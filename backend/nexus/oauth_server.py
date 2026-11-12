"""Restricted OAuth authorization-code flow, pre-registered clients only.

Not yet a publicly deployable OAuth server. No refresh tokens or dynamic registration.
"""
import secrets
from urllib.parse import urlencode

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .db import connection
from .identity import current_user, token_digest
from .oauth_pkce import CHALLENGE_PATTERN, validate_redirect_uri, verify_pkce

RESOURCE = "nexus-mcp"


class AuthorizeRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=255)
    redirect_uri: str = Field(min_length=1, max_length=2048)
    response_type: str
    code_challenge: str
    code_challenge_method: str
    state: str = Field(min_length=8, max_length=1024)
    scope: str = Field(default="mcp:read", max_length=256)
    consent: bool = False


class TokenRequest(BaseModel):
    grant_type: str
    code: str
    client_id: str
    redirect_uri: str
    code_verifier: str


def authorize(payload: AuthorizeRequest, request: Request) -> dict:
    # Explicit POST is the user consent action, not an automatic GET redirect.
    user = current_user(request)
    if not payload.consent:
        raise HTTPException(400, "Explicit consent required")
    if payload.response_type != "code" or payload.code_challenge_method != "S256":
        raise HTTPException(400, "Unsupported OAuth flow")
    if not CHALLENGE_PATTERN.fullmatch(payload.code_challenge) or payload.scope != "mcp:read":
        raise HTTPException(400, "Invalid PKCE challenge or scope")
    if not validate_redirect_uri(payload.redirect_uri):
        raise HTTPException(400, "Invalid redirect URI")
    with connection() as conn:
        client = conn.execute(
            "SELECT redirect_uris FROM oauth_clients WHERE client_id=%s AND disabled_at IS NULL",
            (payload.client_id,),
        ).fetchone()
        if not client or payload.redirect_uri not in client[0]:
            raise HTTPException(400, "Unregistered client or redirect URI")
        code = secrets.token_urlsafe(48)
        conn.execute(
            """INSERT INTO oauth_authorization_codes
               (code_hash,client_id,user_id,redirect_uri,code_challenge,scope,expires_at)
               VALUES (%s,%s,%s,%s,%s,%s,now()+interval '3 minutes')""",
            (token_digest(code),payload.client_id,user["id"],payload.redirect_uri,payload.code_challenge,payload.scope),
        )
    return {"redirect_uri": payload.redirect_uri + ("&" if "?" in payload.redirect_uri else "?") + urlencode({"code":code,"state":payload.state})}


def exchange(payload: TokenRequest) -> dict:
    if payload.grant_type != "authorization_code" or not payload.code or len(payload.code)>512:
        raise HTTPException(400, "Invalid grant")
    if not validate_redirect_uri(payload.redirect_uri) or len(payload.client_id)>255:
        raise HTTPException(400, "Invalid grant")
    with connection() as conn:
        # Lock the code row so concurrent exchanges cannot both succeed.
        with conn.transaction():
            row = conn.execute(
                """SELECT client_id,user_id,redirect_uri,code_challenge,scope
                   FROM oauth_authorization_codes
                   WHERE code_hash=%s AND consumed_at IS NULL AND expires_at>now()
                   FOR UPDATE""",
                (token_digest(payload.code),),
            ).fetchone()
            if not row or row[0]!=payload.client_id or row[2]!=payload.redirect_uri or not verify_pkce(payload.code_verifier,row[3]):
                raise HTTPException(400, "Invalid or expired authorization code")
            client = conn.execute(
                "SELECT 1 FROM oauth_clients WHERE client_id=%s AND disabled_at IS NULL AND %s=ANY(redirect_uris)",
                (payload.client_id,payload.redirect_uri),
            ).fetchone()
            if not client:
                raise HTTPException(400, "Client disabled")
            conn.execute("UPDATE oauth_authorization_codes SET consumed_at=now() WHERE code_hash=%s", (token_digest(payload.code),))
            token = secrets.token_urlsafe(48)
            conn.execute(
                """INSERT INTO oauth_access_tokens(token_hash,client_id,user_id,audience,scope,expires_at)
                   VALUES (%s,%s,%s,%s,%s,now()+interval '30 minutes')""",
                (token_digest(token),payload.client_id,row[1],RESOURCE,row[4]),
            )
    return {"access_token":token,"token_type":"Bearer","expires_in":1800,"scope":row[4]}


def oauth_token_identity(token: str) -> bool:
    if not token or len(token)>512:
        return False
    with connection() as conn:
        return bool(conn.execute(
            """SELECT 1 FROM oauth_access_tokens t
               JOIN users u ON u.id=t.user_id
               JOIN oauth_clients c ON c.client_id=t.client_id
               JOIN user_roles ur ON ur.user_id=u.id
               WHERE t.token_hash=%s AND t.revoked_at IS NULL AND t.expires_at>now()
               AND t.audience=%s AND t.scope='mcp:read'
               AND u.disabled_at IS NULL AND c.disabled_at IS NULL
               AND ur.role_id IN ('owner','operator','viewer') LIMIT 1""",
            (token_digest(token),RESOURCE),
        ).fetchone())


def consent_preview(client_id: str, redirect_uri: str, request: Request) -> dict:
    """Read-only preview; never issues a code or auto-approves."""
    user = current_user(request)
    if not validate_redirect_uri(redirect_uri):
        raise HTTPException(400, "Invalid redirect URI")
    with connection() as conn:
        row = conn.execute(
            "SELECT client_name,redirect_uris FROM oauth_clients WHERE client_id=%s AND disabled_at IS NULL",
            (client_id,),
        ).fetchone()
    if not row or redirect_uri not in row[1]:
        raise HTTPException(400, "Unregistered client or redirect URI")
    return {"client_id": client_id, "client_name": row[0], "redirect_uri": redirect_uri,
            "scope": "mcp:read", "username": user["username"],
            "consent_required": True, "execution_enabled": False}


class RevokeRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=255)


def revoke_client_tokens(payload: RevokeRequest, request: Request) -> dict:
    user = current_user(request)
    with connection() as conn:
        result = conn.execute(
            """UPDATE oauth_access_tokens SET revoked_at=now()
               WHERE user_id=%s AND client_id=%s AND revoked_at IS NULL""",
            (user["id"], payload.client_id),
        )
    return {"revoked": result.rowcount}
