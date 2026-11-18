"""Regras de eventos e programação (determinísticas)."""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession, selectinload

from app.core.errors import Conflict, DomainError, NotFound
from app.modules.activity.service import record
from app.modules.events.models import Event, EventStatus, Room, Session, SessionStatus, Speaker
from app.modules.events.schemas import EventIn, EventUpdateIn, SessionIn, SessionUpdateIn


def get_event(db: DbSession, id_or_slug: str) -> Event:
    event = db.scalar(select(Event).where(or_(Event.id == id_or_slug, Event.slug == id_or_slug)))
    if not event:
        raise NotFound("Event not found")
    return event


def list_events(db: DbSession, *, status: str | None = None, q: str | None = None, category: str | None = None) -> list[dict]:
    stmt = select(Event).order_by(Event.start_at)
    if status:
        stmt = stmt.where(Event.status == status)
    if category:
        stmt = stmt.where(Event.category == category)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Event.title).like(like), func.lower(Event.description).like(like)))
    events = list(db.scalars(stmt))
    stats = {
        row.event_id: row
        for row in db.execute(
            select(
                Session.event_id,
                func.count(Session.id).label("n"),
                func.coalesce(func.sum(Session.max_capacity), 0).label("cap"),
                func.coalesce(func.sum(Session.max_capacity - Session.available_spots), 0).label("occ"),
            )
            .where(Session.status != SessionStatus.CANCELLED)
            .group_by(Session.event_id)
        )
    }
    out = []
    for e in events:
        s = stats.get(e.id)
        out.append({"event": e, "sessions_count": s.n if s else 0, "total_capacity": s.cap if s else 0, "total_registered": s.occ if s else 0})
    return out


def list_sessions(
    db: DbSession, event_id: str, *, day: str | None = None, kind: str | None = None, include_cancelled: bool = True
) -> list[Session]:
    stmt = (
        select(Session)
        .where(Session.event_id == event_id)
        .options(selectinload(Session.room), selectinload(Session.speakers))
        .order_by(Session.start_at, Session.code)
    )
    if kind:
        stmt = stmt.where(Session.kind == kind)
    if not include_cancelled:
        stmt = stmt.where(Session.status != SessionStatus.CANCELLED)
    sessions = list(db.scalars(stmt))
    if day:  # AAAA-MM-DD no fuso do evento (a data já vem com offset)
        sessions = [s for s in sessions if s.start_at.astimezone(_tz_of(s.event)).date().isoformat() == day]
    return sessions


def _tz_of(event: Event):
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/Campo_Grande")


def get_session(db: DbSession, session_id_or_code: str, event_id: str | None = None) -> Session:
    stmt = select(Session).options(selectinload(Session.room), selectinload(Session.speakers))
    if event_id:
        stmt = stmt.where(Session.event_id == event_id, or_(Session.id == session_id_or_code, Session.code == session_id_or_code))
    else:
        stmt = stmt.where(Session.id == session_id_or_code)
    session = db.scalar(stmt)
    if not session:
        raise NotFound("Session not found")
    return session


def create_event(db: DbSession, body: EventIn, actor) -> Event:
    if body.end_at <= body.start_at:
        raise DomainError("end_at must be after start_at")
    if db.scalar(select(Event).where(Event.slug == body.slug)):
        raise Conflict("Slug already in use")
    event = Event(**body.model_dump())
    if actor.role == "organizer":
        event.organizers.append(actor)
    db.add(event)
    db.flush()
    record(db, entity_type="event", entity_id=event.id, action="event.created", message=event.title, actor=actor)
    return event


def update_event(db: DbSession, event: Event, body: EventUpdateIn, actor) -> Event:
    data = body.model_dump(exclude_unset=True)
    if event.status == EventStatus.CANCELLED and data.get("status") not in (None, EventStatus.CANCELLED):
        raise Conflict("A cancelled event cannot be reopened")
    for k, v in data.items():
        setattr(event, k, v)
    if event.end_at <= event.start_at:
        raise DomainError("end_at must be after start_at")
    record(db, entity_type="event", entity_id=event.id, action="event.updated", payload={"fields": sorted(data)}, actor=actor)
    return event


def create_session(db: DbSession, event: Event, body: SessionIn, actor) -> Session:
    data = body.model_dump(exclude={"speaker_ids"})
    session = Session(event_id=event.id, available_spots=body.max_capacity, **data)
    if body.speaker_ids:
        session.speakers = list(db.scalars(select(Speaker).where(Speaker.id.in_(body.speaker_ids), Speaker.event_id == event.id)))
    validate_slot(db, session)
    db.add(session)
    db.flush()
    record(db, entity_type="session", entity_id=session.id, action="session.created", message=session.title, actor=actor)
    return session


def update_session(db: DbSession, session: Session, body: SessionUpdateIn, actor) -> Session:
    data = body.model_dump(exclude_unset=True)
    if "max_capacity" in data:
        # D2 herdada: alterar a capacidade preserva as vagas ocupadas.
        occupied = session.occupied
        if data["max_capacity"] < occupied:
            raise Conflict(f"Capacity below occupied spots ({occupied})")
        session.max_capacity = data.pop("max_capacity")
        session.available_spots = session.max_capacity - occupied
        if session.status != SessionStatus.CANCELLED:
            session.status = SessionStatus.SOLD_OUT if session.available_spots == 0 else SessionStatus.PUBLISHED
    for k, v in data.items():
        setattr(session, k, v)
    validate_slot(db, session)
    record(db, entity_type="session", entity_id=session.id, action="session.updated", payload={"fields": sorted(body.model_dump(exclude_unset=True))}, actor=actor)
    return session


def room_conflicts(db: DbSession, room_id: str, start_at: datetime, end_at: datetime, exclude_session_id: str | None = None) -> list[Session]:
    stmt = select(Session).where(
        Session.room_id == room_id,
        Session.status != SessionStatus.CANCELLED,
        Session.start_at < end_at,
        Session.end_at > start_at,
    )
    if exclude_session_id:
        stmt = stmt.where(Session.id != exclude_session_id)
    return list(db.scalars(stmt))


def speaker_conflicts(db: DbSession, speaker_ids: list[str], start_at: datetime, end_at: datetime, exclude_session_id: str | None = None) -> list[Session]:
    if not speaker_ids:
        return []
    from app.modules.events.models import session_speakers

    stmt = (
        select(Session)
        .join(session_speakers, session_speakers.c.session_id == Session.id)
        .where(
            session_speakers.c.speaker_id.in_(speaker_ids),
            Session.status != SessionStatus.CANCELLED,
            Session.start_at < end_at,
            Session.end_at > start_at,
        )
    )
    if exclude_session_id:
        stmt = stmt.where(Session.id != exclude_session_id)
    return list(db.scalars(stmt).unique())


def validate_slot(db: DbSession, session: Session) -> None:
    """Sala existe no mesmo evento, está disponível, comporta os inscritos e não está ocupada no horário."""
    if session.end_at <= session.start_at:
        raise DomainError("end_at must be after start_at")
    event = session.event or db.get(Event, session.event_id)
    if session.start_at < event.start_at or session.end_at > event.end_at:
        raise DomainError("Session must be within the event period", code="outside_event_period")
    if session.room_id:
        room = db.get(Room, session.room_id)
        if not room or room.event_id != session.event_id:
            raise NotFound("Room not found in this event")
        if not room.available:
            raise Conflict(f"Room {room.name} is unavailable", code="room_unavailable")
        if room.capacity < (session.max_capacity - session.available_spots):
            raise Conflict(f"Room {room.name} holds {room.capacity}, session has {session.occupied} registered", code="room_too_small")
        clash = room_conflicts(db, room.id, session.start_at, session.end_at, exclude_session_id=session.id)
        if clash:
            raise Conflict(f"Room {room.name} is busy with {clash[0].code}", code="room_busy", details={"sessions": [c.code for c in clash]})
    clash = speaker_conflicts(db, [s.id for s in session.speakers], session.start_at, session.end_at, exclude_session_id=session.id)
    if clash:
        raise Conflict(f"Speaker already presenting {clash[0].code} at this time", code="speaker_busy", details={"sessions": [c.code for c in clash]})
