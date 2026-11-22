"""Paginação por offset para as listagens do painel.

As rotas devolvem um envelope {items, total, limit, offset}: o front mostra só uma página por vez
e ainda sabe quantos registros existem no total (para "Mostrando 51–100 de 1.234")."""

from typing import Any, Callable, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session as DbSession

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams:
    """Dependência: ?limit=50&offset=0 com limites validados."""

    def __init__(self, limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE), offset: int = Query(default=0, ge=0)):
        self.limit = limit
        self.offset = offset


def paginate(db: DbSession, stmt: Select, params: PageParams, transform: Callable[[Any], Any] | None = None) -> dict:
    """Conta o total (sem ORDER BY) e busca apenas a página pedida."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = list(db.scalars(stmt.limit(params.limit).offset(params.offset)))
    return {"items": [transform(r) for r in rows] if transform else rows, "total": total, "limit": params.limit, "offset": params.offset}


def text_filter(q: str | None, *columns):
    """Condição ILIKE '%q%' em qualquer uma das colunas (None se a busca estiver vazia)."""
    term = (q or "").strip()
    if not term:
        return None
    pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return or_(*(col.ilike(pattern, escape="\\") for col in columns))


def split_values(value: str | None) -> list[str]:
    """'A,B' -> ['A', 'B']; permite filtrar por vários status de uma vez (ex.: abas de histórico)."""
    return [v.strip() for v in (value or "").split(",") if v.strip()]
