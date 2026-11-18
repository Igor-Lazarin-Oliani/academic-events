from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.deps import get_current_user, managed_event_ids
from app.core.errors import Conflict, Unauthorized
from app.core.security import create_token, hash_password, verify_password
from app.modules.auth.models import Role, User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=100)
    course: str | None = None


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    course: str | None = None
    managed_event_ids: list[str] | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def user_out(db: DbSession, user: User) -> UserOut:
    ids = managed_event_ids(db, user) if user.role in (Role.ORGANIZER, Role.STAFF, Role.ADMIN) else set()
    return UserOut(id=user.id, name=user.name, email=user.email, role=user.role, course=user.course,
                   managed_event_ids=None if ids is None else sorted(ids))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DbSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if not user or not verify_password(body.password, user.password_hash):
        raise Unauthorized("Invalid email or password")
    return TokenOut(access_token=create_token(user.id, user.role), user=user_out(db, user))


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: DbSession = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise Conflict("Email already registered")
    user = User(name=body.name, email=email, password_hash=hash_password(body.password), role=Role.PARTICIPANT, course=body.course)
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_token(user.id, user.role), user=user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return user_out(db, user)
