import uuid
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import JSON

from app.core.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON, datetime: DateTime(timezone=True)}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


_engine = None
_SessionLocal: sessionmaker | None = None


def configure(url: str | None = None) -> None:
    """(Re)configura o engine. Os testes chamam com a URL do banco de teste."""
    global _engine, _SessionLocal
    # Datas saem no fuso do evento (Campo Grande, UTC-4): mais legível para a UI e para o agente.
    _engine = create_engine(url or get_settings().database_url, pool_pre_ping=True, future=True,
                            connect_args={"options": "-c timezone=America/Campo_Grande"})
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def engine():
    if _engine is None:
        configure()
    return _engine


def session_factory() -> sessionmaker:
    if _SessionLocal is None:
        configure()
    return _SessionLocal


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    import app.models  # noqa: F401  (registra todas as tabelas)

    Base.metadata.create_all(engine())
