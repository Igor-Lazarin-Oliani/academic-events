"""Eventos e programação: evento → sessões (palestras, minicursos...) → salas e palestrantes.
As vagas ficam na sessão: é nela que o participante se inscreve."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, new_id


class EventStatus(StrEnum):
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"
    FINISHED = "FINISHED"


class SessionStatus(StrEnum):
    PUBLISHED = "PUBLISHED"
    SOLD_OUT = "SOLD_OUT"
    CANCELLED = "CANCELLED"


class SessionKind(StrEnum):
    PALESTRA = "PALESTRA"
    MINICURSO = "MINICURSO"
    MESA_REDONDA = "MESA_REDONDA"
    WORKSHOP = "WORKSHOP"
    ABERTURA = "ABERTURA"


event_organizers = Table(
    "event_organizers",
    Base.metadata,
    Column("event_id", String(36), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

session_speakers = Table(
    "session_speakers",
    Base.metadata,
    Column("session_id", String(36), ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("speaker_id", String(36), ForeignKey("speakers.id", ondelete="CASCADE"), primary_key=True),
)


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), default="ACADEMIC")
    modality: Mapped[str] = mapped_column(String(20), default="IN_PERSON")
    location: Mapped[str] = mapped_column(String(300))
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(20), default=EventStatus.PUBLISHED)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    max_minicursos_per_participant: Mapped[int] = mapped_column(Integer, default=3)

    sessions: Mapped[list["Session"]] = relationship(back_populates="event", order_by="Session.start_at")
    rooms: Mapped[list["Room"]] = relationship(back_populates="event", order_by="Room.name")
    organizers = relationship("User", secondary=event_organizers)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    building: Mapped[str] = mapped_column(String(120), default="")
    capacity: Mapped[int] = mapped_column(Integer)
    resources: Mapped[list] = mapped_column(default=list)  # ex.: ["projetor", "computadores"]
    available: Mapped[bool] = mapped_column(default=True)

    event: Mapped[Event] = relationship(back_populates="rooms")


class Speaker(Base):
    __tablename__ = "speakers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    affiliation: Mapped[str] = mapped_column(String(200), default="")
    bio: Mapped[str] = mapped_column(Text, default="")


class Session(TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("max_capacity > 0", name="ck_sessions_capacity_positive"),
        CheckConstraint("available_spots >= 0 AND available_spots <= max_capacity", name="ck_sessions_spots_range"),
        CheckConstraint("end_at > start_at", name="ck_sessions_period"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(20))  # ex.: S12, legível para humanos e para o agente
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default=SessionKind.PALESTRA)
    track: Mapped[str] = mapped_column(String(80), default="Geral")
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    max_capacity: Mapped[int] = mapped_column(Integer)
    # Só a reserva, a devolução e a alteração de capacidade mudam este valor (como no events-tickets-ms).
    available_spots: Mapped[int] = mapped_column(Integer)
    workload_hours: Mapped[int] = mapped_column(Integer, default=2)
    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.PUBLISHED)

    event: Mapped[Event] = relationship(back_populates="sessions")
    room: Mapped[Room | None] = relationship()
    speakers: Mapped[list[Speaker]] = relationship(secondary=session_speakers)

    @property
    def occupied(self) -> int:
        return self.max_capacity - self.available_spots
