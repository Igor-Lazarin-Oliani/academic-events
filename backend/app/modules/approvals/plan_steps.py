"""Passos de um plano de ação (L3). Cada passo tem schema, validação (usada ao propor, com
rollback, e de novo ao executar) e execução determinística. O agente só escolhe os passos;
quem valida e aplica é este código."""

from datetime import datetime
from typing import Annotated, Literal, Union

from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, TypeAdapter, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import Conflict, DomainError, NotFound
from app.modules.activity.service import record
from app.modules.events.models import Room, Session, SessionStatus
from app.modules.events.service import validate_slot
from app.modules.notifications.service import notify
from app.modules.tickets.models import Ticket, TicketStatus
from app.modules.tickets.service import cancel_ticket

EVENT_TZ = ZoneInfo("America/Campo_Grande")


class ChangeRoom(BaseModel):
    type: Literal["CHANGE_ROOM"] = "CHANGE_ROOM"
    session_code: str
    room_name: str


class RescheduleSession(BaseModel):
    type: Literal["RESCHEDULE_SESSION"] = "RESCHEDULE_SESSION"
    session_code: str
    start_at: datetime
    end_at: datetime
    room_name: str | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _localize(cls, v: datetime) -> datetime:
        # Horário sem fuso vindo do modelo é interpretado no fuso do evento.
        return v.replace(tzinfo=EVENT_TZ) if v.tzinfo is None else v


class CancelSession(BaseModel):
    type: Literal["CANCEL_SESSION"] = "CANCEL_SESSION"
    session_code: str
    reason: str = Field(min_length=3, max_length=300)


class MarkRoomUnavailable(BaseModel):
    type: Literal["MARK_ROOM_UNAVAILABLE"] = "MARK_ROOM_UNAVAILABLE"
    room_name: str
    reason: str = ""


class NotifyParticipants(BaseModel):
    type: Literal["NOTIFY_PARTICIPANTS"] = "NOTIFY_PARTICIPANTS"
    session_codes: list[str] = Field(min_length=1)
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=3000)


PlanStep = Annotated[Union[ChangeRoom, RescheduleSession, CancelSession, MarkRoomUnavailable, NotifyParticipants], Field(discriminator="type")]
plan_adapter = TypeAdapter(list[PlanStep])


def parse_steps(raw: list[dict]) -> list:
    return plan_adapter.validate_python(raw)


def _session(db: DbSession, event_id: str, code: str) -> Session:
    s = db.scalar(select(Session).where(Session.event_id == event_id, Session.code == code))
    if not s:
        raise NotFound(f"Session {code} not found in this event")
    return s


def _room(db: DbSession, event_id: str, name: str) -> Room:
    r = db.scalar(select(Room).where(Room.event_id == event_id, Room.name == name))
    if not r:
        raise NotFound(f"Room '{name}' not found in this event")
    return r


def _recipients(db: DbSession, session_ids: list[str], proposal_id: str) -> list[str]:
    """Inscritos ativos e também os que tiveram o ingresso cancelado por este mesmo plano."""
    rows = db.scalars(
        select(Ticket.user_id).where(
            Ticket.session_id.in_(session_ids),
            (Ticket.status != TicketStatus.CANCELLED) | (Ticket.cancel_reason == f"plan:{proposal_id}"),
        )
    )
    return list(dict.fromkeys(rows))


def apply_step(db: DbSession, event_id: str, step, *, proposal_id: str, actor) -> dict:
    """Aplica um passo e devolve o resultado. Lança DomainError se o passo não for válido."""
    meta = {"proposal_id": proposal_id}
    if isinstance(step, ChangeRoom):
        s, r = _session(db, event_id, step.session_code), _room(db, event_id, step.room_name)
        old = s.room.name if s.room else None
        s.room_id = r.id
        s.room = r
        validate_slot(db, s)
        record(db, entity_type="session", entity_id=s.id, action="session.room_changed", source="agent", actor=actor, payload={**meta, "from": old, "to": r.name})
        return {"session": s.code, "from_room": old, "to_room": r.name}

    if isinstance(step, RescheduleSession):
        s = _session(db, event_id, step.session_code)
        before = {"start_at": s.start_at.isoformat(), "end_at": s.end_at.isoformat(), "room": s.room.name if s.room else None}
        s.start_at, s.end_at = step.start_at, step.end_at
        if step.room_name:
            r = _room(db, event_id, step.room_name)
            s.room_id, s.room = r.id, r
        validate_slot(db, s)
        after = {"start_at": s.start_at.isoformat(), "end_at": s.end_at.isoformat(), "room": s.room.name if s.room else None}
        record(db, entity_type="session", entity_id=s.id, action="session.rescheduled", source="agent", actor=actor, payload={**meta, "before": before, "after": after})
        return {"session": s.code, "before": before, "after": after}

    if isinstance(step, CancelSession):
        s = _session(db, event_id, step.session_code)
        if s.status == SessionStatus.CANCELLED:
            raise Conflict(f"Session {s.code} already cancelled")
        tickets = list(db.scalars(select(Ticket).where(Ticket.session_id == s.id, Ticket.status != TicketStatus.CANCELLED)))
        for t in tickets:  # cascata (como o cancelamento de evento no events-tickets-ms)
            cancel_ticket(db, t, actor=actor, reason=f"plan:{proposal_id}", source="agent", allow_checked_in=True)
        s.status = SessionStatus.CANCELLED
        record(db, entity_type="session", entity_id=s.id, action="session.cancelled", source="agent", actor=actor, message=step.reason, payload={**meta, "tickets_cancelled": len(tickets)})
        return {"session": s.code, "tickets_cancelled": len(tickets)}

    if isinstance(step, MarkRoomUnavailable):
        r = _room(db, event_id, step.room_name)
        r.available = False
        record(db, entity_type="room", entity_id=r.id, action="room.unavailable", source="agent", actor=actor, message=step.reason, payload=meta)
        return {"room": r.name, "available": False}

    if isinstance(step, NotifyParticipants):
        sessions = [_session(db, event_id, c) for c in step.session_codes]
        users = _recipients(db, [s.id for s in sessions], proposal_id)
        n = notify(db, user_ids=users, title=step.title, body=step.body, link="/meus-ingressos", proposal_id=proposal_id)
        record(db, entity_type="proposal", entity_id=proposal_id, action="participants.notified", source="agent", actor=actor, payload={"sessions": step.session_codes, "recipients": n})
        return {"sessions": step.session_codes, "recipients": n}

    raise DomainError(f"Unknown step type {type(step).__name__}")
