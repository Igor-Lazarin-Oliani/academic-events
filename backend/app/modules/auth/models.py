from enum import StrEnum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, new_id


class Role(StrEnum):
    PARTICIPANT = "participant"
    STAFF = "staff"          # credenciamento (check-in)
    ORGANIZER = "organizer"  # comissão organizadora de eventos específicos
    ADMIN = "admin"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default=Role.PARTICIPANT)
    course: Mapped[str | None] = mapped_column(String(120), nullable=True)
