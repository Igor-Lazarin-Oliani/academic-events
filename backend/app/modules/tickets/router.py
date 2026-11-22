import csv
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.deps import ensure_can_manage_event, get_current_user, require_roles
from app.core.errors import Forbidden
from app.core.pagination import Page, PageParams, paginate
from app.modules.auth.models import User
from app.modules.events.schemas import SessionOut
from app.modules.tickets import service

router = APIRouter(tags=["tickets"])
_TZ = ZoneInfo("America/Campo_Grande")


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ticket_code: str
    user_id: str
    event_id: str
    session_id: str
    status: str
    checked_in_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    created_at: datetime
    session: SessionOut | None = None


class AttendeeOut(TicketOut):
    participant_name: str
    participant_email: str


class IssueIn(BaseModel):
    session_id: str
    ticket_id: str | None = None  # opcional: chave de idempotência gerada pelo cliente


class SwapIn(BaseModel):
    to_session_id: str


class CheckInIn(BaseModel):
    code: str
    event_id: str | None = None


class CancelIn(BaseModel):
    reason: str = ""


@router.post("/tickets", response_model=TicketOut, status_code=201)
def issue(body: IssueIn, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    ticket = service.issue_ticket(db, user=user, session_id=body.session_id, ticket_id=body.ticket_id)
    db.commit()
    return service.get_ticket(db, ticket.id)


@router.get("/me/tickets", response_model=list[TicketOut])
def my_tickets(event_id: str | None = None, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return service.list_tickets(db, user_id=user.id, event_id=event_id)


@router.get("/tickets/{id_or_code}", response_model=TicketOut)
def get_ticket(id_or_code: str, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    ticket = service.get_ticket(db, id_or_code)
    if ticket.user_id != user.id:
        ensure_can_manage_event(db, user, ticket.event_id)
    return ticket


@router.post("/tickets/{ticket_id}/cancel", response_model=TicketOut)
def cancel(ticket_id: str, body: CancelIn | None = None, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    ticket = service.get_ticket(db, ticket_id)
    if ticket.user_id != user.id:
        ensure_can_manage_event(db, user, ticket.event_id)
    service.cancel_ticket(db, ticket, actor=user, reason=(body.reason if body else ""))
    db.commit()
    return service.get_ticket(db, ticket.id)


@router.post("/tickets/{ticket_id}/swap", response_model=TicketOut)
def swap(ticket_id: str, body: SwapIn, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    ticket = service.get_own_ticket(db, user, ticket_id)
    new = service.swap_session(db, user=user, ticket=ticket, to_session_id=body.to_session_id)
    db.commit()
    return service.get_ticket(db, new.id)


@router.post("/checkin", response_model=AttendeeOut)
def check_in(body: CheckInIn, user: User = Depends(require_roles("staff", "organizer", "admin")), db: DbSession = Depends(get_db)):
    ticket = service.get_ticket(db, body.code)
    ensure_can_manage_event(db, user, ticket.event_id)
    service.check_in(db, code=body.code, actor=user, event_id=body.event_id)
    db.commit()
    t = service.get_ticket(db, ticket.id)
    return AttendeeOut(**TicketOut.model_validate(t).model_dump(), participant_name=t.user.name, participant_email=t.user.email)


def _to_attendee(t) -> AttendeeOut:
    return AttendeeOut(**TicketOut.model_validate(t).model_dump(), participant_name=t.user.name, participant_email=t.user.email)


def _attendees_scope(db: DbSession, user: User, event_id: str, session_id: str | None, status: str | None) -> None:
    ensure_can_manage_event(db, user, event_id)
    if session_id is None and status is None and user.role == "staff":
        raise Forbidden("Staff must filter by session")


@router.get("/events/{event_id}/attendees", response_model=Page[AttendeeOut])
def attendees(event_id: str, session_id: str | None = None, status: str | None = None, q: str | None = None,
              page: PageParams = Depends(), user: User = Depends(require_roles("staff", "organizer", "admin")), db: DbSession = Depends(get_db)):
    _attendees_scope(db, user, event_id, session_id, status)
    stmt = service.attendees_query(event_id=event_id, session_id=session_id, status=status, q=q)
    return paginate(db, stmt, page, _to_attendee)


_STATUS_LABEL = {"CONFIRMED": "Confirmado", "CHECKED_IN": "Presença registrada", "CANCELLED": "Cancelado"}


@router.get("/events/{event_id}/attendees/export")
def export_attendees(event_id: str, session_id: str | None = None, status: str | None = None, q: str | None = None,
                     user: User = Depends(require_roles("staff", "organizer", "admin")), db: DbSession = Depends(get_db)):
    """CSV com TODOS os inscritos que batem com os filtros (a tela só carrega uma página por vez)."""
    _attendees_scope(db, user, event_id, session_id, status)
    stmt = service.attendees_query(event_id=event_id, session_id=session_id, status=status, q=q)
    buf = io.StringIO()
    buf.write("﻿")  # BOM: o Excel abre acentos corretamente
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["Código", "Nome", "E-mail", "Sessão", "Status", "Check-in"])
    for t in db.scalars(stmt):
        checked = t.checked_in_at.astimezone(_TZ).strftime("%d/%m %H:%M") if t.checked_in_at else ""
        w.writerow([t.ticket_code, t.user.name, t.user.email, t.session.code if t.session else "", _STATUS_LABEL.get(t.status, t.status), checked])
    return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="inscritos.csv"'})
