from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, new_id
from app.modules.auth.models import User
from app.modules.events.models import Session


class TicketStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CANCELLED = "CANCELLED"


class Ticket(TimestampMixin, Base):
    """Inscrição = ingresso (mesma entidade do events-tickets-ms), agora por sessão."""

    __tablename__ = "tickets"
    __table_args__ = (
        # D3 herdada: uma inscrição ativa por pessoa em cada sessão. Quem cancelou pode voltar.
        Index(
            "ux_tickets_active_user_session",
            "user_id",
            "session_id",
            unique=True,
            postgresql_where=text("status <> 'CANCELLED'"),
        ),
    )

    # O id é gerado antes da reserva e serve de chave de idempotência.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=TicketStatus.CONFIRMED, index=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    user: Mapped[User] = relationship()
    session: Mapped[Session] = relationship()
