"""Password-based operator sessions. OAuth authorization server is a separate milestone."""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field

from .db import connection

COOKIE_NAME = "nexus_session"
USERNAME = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")


def hash_password(password: str) -> str:
    if len(password) < 14 or len(password) > 1024:
        raise ValueError("Password length must be between 14 and 1024")
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=128*1024*1024)
    return "scrypt$32768$8$1$" + salt.hex() + "$" + derived.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt" or (int(n), int(r), int(p)) != (32768, 8, 1):
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32, maxmem=128*1024*1024)
        return hmac.compare_digest(candidate, bytes.fromhex(expected))
    except (ValueError, TypeError, OverflowError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


def login(payload: LoginRequest, response: Response) -> dict:
    username = payload.username.lower()
    if not USERNAME.fullmatch(username):
        raise HTTPException(401, "Invalid credentials")
    with connection() as conn:
        recent = conn.execute(
            "SELECT count(*) FROM login_attempts WHERE username=%s AND occurred_at > now()-interval '15 minutes' AND NOT succeeded",
            (username,),
        ).fetchone()[0]
        if recent >= 5:
            raise HTTPException(429, "Too many attempts")
        row = conn.execute(
            "SELECT id,password_hash FROM users WHERE username=%s AND disabled_at IS NULL",
            (username,),
        ).fetchone()
        valid = bool(row and row[1] and verify_password(payload.password, row[1]))
        conn.execute("INSERT INTO login_attempts(username,succeeded) VALUES (%s,%s)", (username,valid))
        if not valid:
            conn.commit()
            raise HTTPException(401, "Invalid credentials")
        token = secrets.token_urlsafe(48)
        conn.execute(
            "INSERT INTO user_sessions(user_id,token_hash,expires_at) VALUES (%s,%s,now()+interval '12 hours')",
            (row[0],token_digest(token)),
        )
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=True, samesite="strict", max_age=43200, path="/api/auth")
    response.headers["Cache-Control"] = "no-store"
    return {"username": username}


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Authentication required")
    with connection() as conn:
        row = conn.execute(
            """SELECT u.id,u.username,COALESCE(array_agg(ur.role_id) FILTER (WHERE ur.role_id IS NOT NULL),ARRAY[]::text[])
               FROM user_sessions s JOIN users u ON u.id=s.user_id
               LEFT JOIN user_roles ur ON ur.user_id=u.id
               WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>now() AND u.disabled_at IS NULL
               GROUP BY u.id,u.username""",
            (token_digest(token),),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Authentication required")
    return {"id":str(row[0]),"username":row[1],"roles":row[2]}


def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with connection() as conn:
            conn.execute("UPDATE user_sessions SET revoked_at=now() WHERE token_hash=%s AND revoked_at IS NULL", (token_digest(token),))
    response.delete_cookie(COOKIE_NAME, path="/api/auth", secure=True, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"ok":True}
