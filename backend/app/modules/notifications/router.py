from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.deps import ensure_can_manage_event, get_current_user, managed_event_ids, require_roles
from app.modules.auth.models import User
from app.modules.notifications import service
from app.modules.notifications.models import SupportRequest

router = APIRouter(tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    body: str
    link: str | None
    read_at: datetime | None
    created_at: datetime


class SupportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    event_id: str | None
    summary: str
    status: str
    answer: str | None
    run_id: str | None
    created_at: datetime


class AnswerIn(BaseModel):
    answer: str


@router.get("/me/notifications", response_model=list[NotificationOut])
def my_notifications(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return service.list_for_user(db, user.id)


@router.post("/me/notifications/read", status_code=204)
def mark_read(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    service.mark_all_read(db, user.id)
    db.commit()


@router.get("/me/support-requests", response_model=list[SupportOut])
def my_requests(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return list(db.scalars(select(SupportRequest).where(SupportRequest.user_id == user.id).order_by(SupportRequest.created_at.desc())))


@router.get("/support-requests", response_model=list[SupportOut])
def list_requests(status: str | None = None, user: User = Depends(require_roles("organizer", "admin")), db: DbSession = Depends(get_db)):
    stmt = select(SupportRequest).order_by(SupportRequest.created_at.desc())
    if status:
        stmt = stmt.where(SupportRequest.status == status)
    ids = managed_event_ids(db, user)
    if ids is not None:
        stmt = stmt.where(SupportRequest.event_id.in_(ids))
    return list(db.scalars(stmt))


@router.post("/support-requests/{req_id}/answer", response_model=SupportOut)
def answer(req_id: str, body: AnswerIn, user: User = Depends(require_roles("organizer", "admin")), db: DbSession = Depends(get_db)):
    req = db.get(SupportRequest, req_id)
    if req and req.event_id:
        ensure_can_manage_event(db, user, req.event_id)
    req = service.answer_support_request(db, req_id, answer=body.answer, actor=user)
    db.commit()
    return req
