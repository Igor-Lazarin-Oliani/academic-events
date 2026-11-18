from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.core.database import utcnow
from app.core.errors import NotFound
from app.modules.activity.service import record
from app.modules.notifications.models import Notification, SupportRequest


def notify(db: DbSession, *, user_ids: list[str], title: str, body: str, link: str | None = None, proposal_id: str | None = None) -> int:
    for uid in dict.fromkeys(user_ids):  # sem duplicar destinatário
        db.add(Notification(user_id=uid, title=title, body=body, link=link, source_proposal_id=proposal_id))
    return len(set(user_ids))


def list_for_user(db: DbSession, user_id: str, limit: int = 50) -> list[Notification]:
    return list(db.scalars(select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(limit)))


def mark_all_read(db: DbSession, user_id: str) -> None:
    db.execute(update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None)).values(read_at=utcnow()))


def open_support_request(db: DbSession, *, user, event_id: str | None, summary: str, run_id: str | None = None, source: str = "agent") -> SupportRequest:
    req = SupportRequest(user_id=user.id, event_id=event_id, summary=summary[:2000], run_id=run_id)
    db.add(req)
    db.flush()
    record(db, entity_type="support_request", entity_id=req.id, action="support.opened", source=source, actor=user, message=summary[:200])
    return req


def answer_support_request(db: DbSession, req_id: str, *, answer: str, actor) -> SupportRequest:
    req = db.get(SupportRequest, req_id)
    if not req:
        raise NotFound("Support request not found")
    req.answer = answer
    req.status = "ANSWERED"
    notify(db, user_ids=[req.user_id], title="Resposta da comissão organizadora", body=answer, link="/minha-conta/chamados")
    record(db, entity_type="support_request", entity_id=req.id, action="support.answered", actor=actor)
    return req
