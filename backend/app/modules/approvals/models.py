"""Propostas de ação. O agente só cria propostas (registra intenção); quem decide é um humano
por uma rota que não é uma tool. A execução é determinística e idempotente."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, new_id


class ProposalKind(StrEnum):
    CANCEL_TICKET = "CANCEL_TICKET"    # L2: o próprio participante confirma
    SWAP_SESSION = "SWAP_SESSION"      # L2: o próprio participante confirma
    ACTION_PLAN = "ACTION_PLAN"        # L3: um organizador do evento aprova


class ProposalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class ActionProposal(TimestampMixin, Base):
    __tablename__ = "action_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    level: Mapped[str] = mapped_column(String(4))  # L2 | L3
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True, index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(default=dict)        # parâmetros ou passos do plano
    impact: Mapped[dict] = mapped_column(default=dict)         # afetados, sessões, salas (calculado no backend)
    communication: Mapped[dict | None] = mapped_column(nullable=True)  # comunicado revisado
    review: Mapped[dict | None] = mapped_column(nullable=True)         # parecer do Revisor
    status: Mapped[str] = mapped_column(String(12), default=ProposalStatus.PENDING, index=True)
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    result: Mapped[dict] = mapped_column(default=dict)         # passos executados (idempotência)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
