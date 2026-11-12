"""Server-side role authorization for operator APIs."""
from fastapi import Depends, HTTPException
from .identity import current_user


def require_role(*allowed: str):
    def check(user: dict = Depends(current_user)) -> dict:
        if not set(user["roles"]).intersection(allowed):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check
