from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.deps import ensure_can_manage_event, require_roles
from app.modules.auth.models import User
from app.modules.events import service
from app.modules.events.models import Room, Session, SessionStatus, Speaker
from app.modules.events.schemas import (
    EventDetailOut,
    EventIn,
    EventOut,
    EventSummaryOut,
    EventUpdateIn,
    RoomOut,
    SessionIn,
    SessionOut,
    SessionUpdateIn,
    SpeakerOut,
)
from app.modules.tickets.models import Ticket, TicketStatus

router = APIRouter(tags=["events"])
manager = require_roles("organizer", "admin")


@router.get("/events", response_model=list[EventSummaryOut])
def list_events(status: str | None = None, q: str | None = None, category: str | None = None, db: DbSession = Depends(get_db)):
    return [
        EventSummaryOut(**EventOut.model_validate(r["event"]).model_dump(), sessions_count=r["sessions_count"],
                        total_capacity=r["total_capacity"], total_registered=r["total_registered"])
        for r in service.list_events(db, status=status, q=q, category=category)
    ]


@router.get("/events/{id_or_slug}", response_model=EventDetailOut)
def get_event(id_or_slug: str, db: DbSession = Depends(get_db)):
    event = service.get_event(db, id_or_slug)
    sessions = service.list_sessions(db, event.id)
    speakers = list(db.scalars(select(Speaker).where(Speaker.event_id == event.id).order_by(Speaker.name)))
    return EventDetailOut(**EventOut.model_validate(event).model_dump(),
                          sessions=[SessionOut.model_validate(s) for s in sessions],
                          rooms=[RoomOut.model_validate(r) for r in event.rooms],
                          speakers=[SpeakerOut.model_validate(s) for s in speakers])


@router.get("/events/{id_or_slug}/sessions", response_model=list[SessionOut])
def list_sessions(id_or_slug: str, day: str | None = None, kind: str | None = None, db: DbSession = Depends(get_db)):
    event = service.get_event(db, id_or_slug)
    return service.list_sessions(db, event.id, day=day, kind=kind)


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: DbSession = Depends(get_db)):
    return service.get_session(db, session_id)


@router.post("/events", response_model=EventOut, status_code=201)
def create_event(body: EventIn, user: User = Depends(manager), db: DbSession = Depends(get_db)):
    event = service.create_event(db, body, user)
    db.commit()
    return event


@router.put("/events/{event_id}", response_model=EventOut)
def update_event(event_id: str, body: EventUpdateIn, user: User = Depends(manager), db: DbSession = Depends(get_db)):
    event = service.get_event(db, event_id)
    ensure_can_manage_event(db, user, event.id)
    service.update_event(db, event, body, user)
    db.commit()
    return event


@router.post("/events/{event_id}/sessions", response_model=SessionOut, status_code=201)
def create_session(event_id: str, body: SessionIn, user: User = Depends(manager), db: DbSession = Depends(get_db)):
    event = service.get_event(db, event_id)
    ensure_can_manage_event(db, user, event.id)
    session = service.create_session(db, event, body, user)
    db.commit()
    return service.get_session(db, session.id)


@router.put("/sessions/{session_id}", response_model=SessionOut)
def update_session(session_id: str, body: SessionUpdateIn, user: User = Depends(manager), db: DbSession = Depends(get_db)):
    session = service.get_session(db, session_id)
    ensure_can_manage_event(db, user, session.event_id)
    service.update_session(db, session, body, user)
    db.commit()
    return service.get_session(db, session.id)


@router.get("/events/{event_id}/dashboard")
def dashboard(event_id: str, user: User = Depends(require_roles("organizer", "staff", "admin")), db: DbSession = Depends(get_db)):
    """KPIs do painel do organizador."""
    event = service.get_event(db, event_id)
    ensure_can_manage_event(db, user, event.id)
    sessions = service.list_sessions(db, event.id)
    counts = dict(
        db.execute(select(Ticket.status, func.count(Ticket.id)).where(Ticket.event_id == event.id).group_by(Ticket.status)).all()
    )
    checked = {sid: n for sid, n in db.execute(
        select(Ticket.session_id, func.count(Ticket.id)).where(Ticket.event_id == event.id, Ticket.status == TicketStatus.CHECKED_IN).group_by(Ticket.session_id))}
    participants = db.scalar(select(func.count(func.distinct(Ticket.user_id))).where(Ticket.event_id == event.id, Ticket.status != TicketStatus.CANCELLED))
    active = [s for s in sessions if s.status != SessionStatus.CANCELLED]
    capacity = sum(s.max_capacity for s in active)
    occupied = sum(s.occupied for s in active)
    return {
        "event_id": event.id,
        "participants": participants or 0,
        "tickets": {"confirmed": counts.get("CONFIRMED", 0), "checked_in": counts.get("CHECKED_IN", 0), "cancelled": counts.get("CANCELLED", 0)},
        "capacity": capacity,
        "occupied": occupied,
        "occupancy_rate": round(occupied / capacity, 3) if capacity else 0,
        "sold_out_sessions": sum(1 for s in active if s.status == SessionStatus.SOLD_OUT),
        "cancelled_sessions": sum(1 for s in sessions if s.status == SessionStatus.CANCELLED),
        "unavailable_rooms": [r.name for r in db.scalars(select(Room).where(Room.event_id == event.id, Room.available.is_(False)))],
        "sessions": [
            {"id": s.id, "code": s.code, "title": s.title, "kind": s.kind, "start_at": s.start_at, "end_at": s.end_at,
             "room": s.room.name if s.room else None, "capacity": s.max_capacity, "occupied": s.occupied,
             "checked_in": checked.get(s.id, 0), "status": s.status}
            for s in sessions
        ],
    }
