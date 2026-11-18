from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.deps import require_roles
from app.modules.activity import service
from app.modules.auth.models import User

router = APIRouter(prefix="/activity", tags=["activity"])
auditor = require_roles("organizer", "admin")


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    occurred_at: datetime
    entity_type: str
    entity_id: str
    action: str
    level: str
    source: str
    actor_id: str | None
    actor_role: str | None
    correlation_id: str | None
    message: str
    payload: dict
    status: str
    notes: str | None
    archived_at: datetime | None


class TriageIn(BaseModel):
    status: str | None = Field(default=None, pattern="^(NEW|REVIEWED|RESOLVED)$")
    notes: str | None = None


@router.get("", response_model=list[ActivityOut])
def list_activity(entity_type: str | None = None, entity_id: str | None = None, action: str | None = None, source: str | None = None,
                  level: str | None = None, status: str | None = None, correlation_id: str | None = None, include_archived: bool = False,
                  limit: int = Query(default=100, ge=1, le=500), offset: int = 0, _: User = Depends(auditor), db: DbSession = Depends(get_db)):
    return service.list_logs(db, entity_type=entity_type, entity_id=entity_id, action=action, source=source, level=level, status=status,
                             correlation_id=correlation_id, include_archived=include_archived, limit=limit, offset=offset)


@router.put("/{log_id}", response_model=ActivityOut)
def triage(log_id: str, body: TriageIn, _: User = Depends(auditor), db: DbSession = Depends(get_db)):
    log = service.triage(db, log_id, status=body.status, notes=body.notes)
    db.commit()
    return log


@router.delete("/{log_id}", response_model=ActivityOut)
def archive(log_id: str, _: User = Depends(auditor), db: DbSession = Depends(get_db)):
    log = service.archive(db, log_id)
    db.commit()
    return log
