from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.modules.auth.models import Role, User
from app.modules.events.models import event_organizers


def get_optional_user(authorization: str | None = Header(default=None), db: DbSession = Depends(get_db)) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
    except Exception as exc:  # token inválido ou expirado
        raise Unauthorized("Invalid or expired token") from exc
    user = db.get(User, payload.get("sub"))
    if not user:
        raise Unauthorized("User not found")
    return user


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise Unauthorized("Authentication required")
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise Forbidden(f"Requires role: {', '.join(roles)}")
        return user

    return checker


def managed_event_ids(db: DbSession, user: User) -> set[str] | None:
    """None = todos (admin). Caso contrário, os eventos que o organizador gerencia."""
    if user.role == Role.ADMIN:
        return None
    rows = db.execute(select(event_organizers.c.event_id).where(event_organizers.c.user_id == user.id))
    return {r[0] for r in rows}


def can_manage_event(db: DbSession, user: User, event_id: str) -> bool:
    if user.role == Role.ADMIN:
        return True
    if user.role not in (Role.ORGANIZER, Role.STAFF):
        return False
    ids = managed_event_ids(db, user)
    return ids is None or event_id in ids


def ensure_can_manage_event(db: DbSession, user: User, event_id: str) -> None:
    if not can_manage_event(db, user, event_id):
        raise Forbidden("You do not manage this event", code="event_out_of_scope")
