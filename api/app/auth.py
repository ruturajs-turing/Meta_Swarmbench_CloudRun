from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import SessionToken, User


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    session = db.get(SessionToken, token)
    if not session or session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    user = db.get(User, session.user_id)
    if not user or user.state != "active":
        raise HTTPException(status_code=401, detail="User is inactive")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role not in {"admin", "platform_admin"}:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
