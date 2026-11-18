"""Inscrições: reserva atômica, idempotência, conflito de horário, limite de minicursos, check-in.

Regras portadas do events-tickets-ms. Como agora é um processo só, reserva e ingresso ficam na
mesma transação e não é preciso compensação. Os serviços não fazem commit: quem chama decide,
o que permite compor operações (ex.: troca = cancelar + emitir, tudo ou nada)."""

import secrets
from datetime import datetime

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.orm import Session as DbSession, selectinload

from app.core.database import new_id, utcnow
from app.core.errors import Conflict, DomainError, Forbidden, NotFound
from app.modules.activity.service import record
from app.modules.events.models import Event, EventStatus, Session, SessionKind, SessionStatus
from app.modules.tickets.models import Ticket, TicketStatus

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_ticket_code(year: int) -> str:
    return f"EVT-{year}-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def reserve_spot(db: DbSession, session_id: str) -> bool:
    """UPDATE condicional: requisições simultâneas nunca vendem mais vagas do que existem."""
    result = db.execute(
        update(Session)
        .where(Session.id == session_id, Session.available_spots > 0, Session.status == SessionStatus.PUBLISHED)
        .values(
            available_spots=Session.available_spots - 1,
            status=text("CASE WHEN available_spots - 1 = 0 THEN 'SOLD_OUT' ELSE status END"),
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def release_spot(db: DbSession, session_id: str) -> None:
    db.execute(
        update(Session)
        .where(Session.id == session_id, Session.available_spots < Session.max_capacity)
        .values(
            available_spots=Session.available_spots + 1,
            status=text("CASE WHEN status = 'SOLD_OUT' THEN 'PUBLISHED' ELSE status END"),
        )
        .execution_options(synchronize_session=False)
    )


def active_tickets_of(db: DbSession, user_id: str, event_id: str | None = None) -> list[Ticket]:
    stmt = (
        select(Ticket)
        .where(Ticket.user_id == user_id, Ticket.status != TicketStatus.CANCELLED)
        .options(selectinload(Ticket.session))
    )
    if event_id:
        stmt = stmt.where(Ticket.event_id == event_id)
    return list(db.scalars(stmt))


def find_time_conflicts(db: DbSession, user_id: str, session: Session) -> list[Ticket]:
    return [
        t
        for t in active_tickets_of(db, user_id, session.event_id)
        if t.session_id != session.id and t.session.start_at < session.end_at and t.session.end_at > session.start_at
    ]


def issue_ticket(db: DbSession, *, user, session_id: str, ticket_id: str | None = None, actor=None, source: str = "api") -> Ticket:
    ticket_id = ticket_id or new_id()
    existing = db.get(Ticket, ticket_id)
    if existing:  # idempotência: repetir com o mesmo id não reserva outra vaga
        return existing

    session = db.get(Session, session_id)
    if not session:
        raise NotFound("Session not found")
    event = db.get(Event, session.event_id)
    if event.status != EventStatus.PUBLISHED:
        raise DomainError("Event is not open for registration", code="event_closed")
    if session.status == SessionStatus.CANCELLED:
        raise DomainError("Session was cancelled", code="session_cancelled")
    if session.end_at <= utcnow():
        raise DomainError("Session has already ended", code="session_ended")

    if db.scalar(select(Ticket).where(Ticket.user_id == user.id, Ticket.session_id == session.id, Ticket.status != TicketStatus.CANCELLED)):
        raise Conflict("You are already registered in this session", code="already_registered")

    conflicts = find_time_conflicts(db, user.id, session)
    if conflicts:
        c = conflicts[0].session
        raise Conflict(
            f"Time conflict with {c.code} - {c.title}",
            code="time_conflict",
            details={"conflicting_session": c.code, "conflicting_ticket": conflicts[0].ticket_code},
        )

    if session.kind == SessionKind.MINICURSO:
        n = db.scalar(
            select(func.count(Ticket.id))
            .join(Session, Session.id == Ticket.session_id)
            .where(and_(Ticket.user_id == user.id, Ticket.event_id == event.id, Ticket.status != TicketStatus.CANCELLED, Session.kind == SessionKind.MINICURSO))
        )
        if n >= event.max_minicursos_per_participant:
            raise Conflict(f"Limit of {event.max_minicursos_per_participant} minicursos per participant reached", code="minicurso_limit")

    if not reserve_spot(db, session.id):
        raise Conflict("Session is sold out", code="sold_out")

    ticket = Ticket(id=ticket_id, ticket_code=new_ticket_code(session.start_at.year), user_id=user.id, event_id=event.id, session_id=session.id)
    db.add(ticket)
    db.flush()
    actor = actor or user
    record(db, entity_type="ticket", entity_id=ticket.id, action="ticket.issued", source=source, actor=actor,
           message=f"{ticket.ticket_code} em {session.code}", payload={"session_id": session.id, "session_code": session.code})
    record(db, entity_type="session", entity_id=session.id, action="session.spot_reserved", source=source, actor=actor, payload={"ticket_id": ticket.id})
    return ticket


def get_ticket(db: DbSession, id_or_code: str) -> Ticket:
    stmt = select(Ticket).options(selectinload(Ticket.session).selectinload(Session.room))
    ticket = db.scalar(stmt.where((Ticket.id == id_or_code) | (Ticket.ticket_code == id_or_code.upper())))
    if not ticket:
        raise NotFound("Ticket not found")
    return ticket


def get_own_ticket(db: DbSession, user, id_or_code: str) -> Ticket:
    """Escopo: o participante só enxerga os próprios ingressos (verificado aqui, não no prompt)."""
    ticket = get_ticket(db, id_or_code)
    if ticket.user_id != user.id:
        raise Forbidden("This ticket belongs to another participant", code="ticket_out_of_scope")
    return ticket


def cancel_ticket(db: DbSession, ticket: Ticket, *, actor, reason: str = "", source: str = "api", allow_checked_in: bool = False) -> Ticket:
    if ticket.status == TicketStatus.CANCELLED:
        raise Conflict("Ticket already cancelled", code="already_cancelled")  # D1: não devolve a vaga duas vezes
    if ticket.status == TicketStatus.CHECKED_IN and not allow_checked_in:
        raise Conflict("Checked-in tickets cannot be cancelled", code="already_checked_in")
    ticket.status = TicketStatus.CANCELLED
    ticket.cancelled_at = utcnow()
    ticket.cancel_reason = reason[:300] if reason else None
    release_spot(db, ticket.session_id)
    db.flush()
    record(db, entity_type="ticket", entity_id=ticket.id, action="ticket.cancelled", source=source, actor=actor, message=reason, payload={"session_id": ticket.session_id})
    record(db, entity_type="session", entity_id=ticket.session_id, action="session.spot_released", source=source, actor=actor, payload={"ticket_id": ticket.id})
    return ticket


def swap_session(db: DbSession, *, user, ticket: Ticket, to_session_id: str, source: str = "api") -> Ticket:
    """Troca = cancelar + emitir na mesma transação. Se a emissão falhar, quem chama faz rollback."""
    if ticket.user_id != user.id:
        raise Forbidden("This ticket belongs to another participant", code="ticket_out_of_scope")
    if ticket.session_id == to_session_id:
        raise DomainError("Ticket is already in this session")
    target = db.get(Session, to_session_id)
    if not target or target.event_id != ticket.event_id:
        raise NotFound("Target session not found in the same event")
    cancel_ticket(db, ticket, actor=user, reason=f"swap to {target.code}", source=source)
    return issue_ticket(db, user=user, session_id=target.id, actor=user, source=source)


def check_in(db: DbSession, *, code: str, actor, event_id: str | None = None) -> Ticket:
    ticket = get_ticket(db, code)
    if event_id and ticket.event_id != event_id:
        raise Forbidden("Ticket belongs to another event", code="ticket_out_of_scope")
    if ticket.status != TicketStatus.CONFIRMED:
        raise Conflict(f"Check-in requires CONFIRMED (current: {ticket.status})", code="invalid_status")
    if ticket.session.status == SessionStatus.CANCELLED:
        raise Conflict("Session was cancelled", code="session_cancelled")
    ticket.status = TicketStatus.CHECKED_IN
    ticket.checked_in_at = utcnow()
    record(db, entity_type="ticket", entity_id=ticket.id, action="ticket.checked_in", actor=actor, payload={"session_id": ticket.session_id})
    return ticket


def list_tickets(
    db: DbSession,
    *,
    user_id: str | None = None,
    event_id: str | None = None,
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[Ticket]:
    stmt = select(Ticket).options(selectinload(Ticket.session).selectinload(Session.room), selectinload(Ticket.user))
    for col, val in ((Ticket.user_id, user_id), (Ticket.event_id, event_id), (Ticket.session_id, session_id), (Ticket.status, status)):
        if val:
            stmt = stmt.where(col == val)
    return list(db.scalars(stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)))


def count_active_by_session(db: DbSession, session_ids: list[str]) -> dict[str, int]:
    if not session_ids:
        return {}
    rows = db.execute(
        select(Ticket.session_id, func.count(Ticket.id))
        .where(Ticket.session_id.in_(session_ids), Ticket.status != TicketStatus.CANCELLED)
        .group_by(Ticket.session_id)
    )
    return {sid: n for sid, n in rows}


