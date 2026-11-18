from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.correlation import current_correlation_id
from app.core.database import utcnow
from app.core.errors import Conflict, NotFound
from app.modules.activity.models import ActivityLog


def record(
    db: DbSession,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    message: str = "",
    level: str = "INFO",
    source: str = "api",
    actor=None,
    payload: dict | None = None,
    correlation_id: str | None = None,
) -> ActivityLog:
    """Grava a atividade na MESMA transação da mudança (o fato e o registro nascem juntos)."""
    log = ActivityLog(
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        message=message,
        level=level,
        source=source,
        actor_id=getattr(actor, "id", None),
        actor_role=getattr(actor, "role", None),
        correlation_id=correlation_id or current_correlation_id(),
        payload=payload or {},
    )
    db.add(log)
    return log


def list_logs(
    db: DbSession,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    source: str | None = None,
    level: str | None = None,
    status: str | None = None,
    correlation_id: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[ActivityLog]:
    q = select(ActivityLog)
    for col, val in (
        (ActivityLog.entity_type, entity_type),
        (ActivityLog.entity_id, entity_id),
        (ActivityLog.action, action),
        (ActivityLog.source, source),
        (ActivityLog.level, level),
        (ActivityLog.status, status),
        (ActivityLog.correlation_id, correlation_id),
    ):
        if val:
            q = q.where(col == val)
    if not include_archived:
        q = q.where(ActivityLog.archived_at.is_(None))
    q = q.order_by(ActivityLog.occurred_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(q))


def triage(db: DbSession, log_id: str, *, status: str | None, notes: str | None) -> ActivityLog:
    log = db.get(ActivityLog, log_id)
    if not log:
        raise NotFound("Activity log not found")
    if log.archived_at:
        raise Conflict("Archived logs cannot be changed")
    if status:
        log.status = status
    if notes is not None:
        log.notes = notes
    return log


def archive(db: DbSession, log_id: str) -> ActivityLog:
    log = db.get(ActivityLog, log_id)
    if not log:
        raise NotFound("Activity log not found")
    log.archived_at = log.archived_at or utcnow()
    return log
