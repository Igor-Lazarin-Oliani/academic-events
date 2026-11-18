"""Rotas de decisão humana. NÃO são expostas como tools: o agente propõe, o humano decide aqui."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.errors import NotFound
from app.modules.approvals import service
from app.modules.approvals.models import ActionProposal
from app.modules.auth.models import User

router = APIRouter(prefix="/proposals", tags=["approvals"])


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str | None
    kind: str
    level: str
    event_id: str | None
    requested_by: str
    title: str
    summary: str
    payload: dict
    impact: dict
    communication: dict | None
    review: dict | None
    status: str
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    executed_at: datetime | None
    result: dict
    error: str | None
    created_at: datetime


class DecisionIn(BaseModel):
    note: str | None = None


@router.get("", response_model=list[ProposalOut])
def list_proposals(status: str | None = None, event_id: str | None = None, kind: str | None = None,
                   user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return service.list_proposals(db, user=user, status=status, event_id=event_id, kind=kind)


@router.get("/{proposal_id}", response_model=ProposalOut)
def get_proposal(proposal_id: str, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    p = db.get(ActionProposal, proposal_id)
    if not p:
        raise NotFound("Proposal not found")
    service.authorize_decision(db, p, user)
    return p


@router.post("/{proposal_id}/approve", response_model=ProposalOut)
def approve(proposal_id: str, body: DecisionIn | None = None, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    p = service.decide(db, proposal_id, user=user, approve=True, note=body.note if body else None)
    db.commit()
    return p


@router.post("/{proposal_id}/reject", response_model=ProposalOut)
def reject(proposal_id: str, body: DecisionIn | None = None, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    p = service.decide(db, proposal_id, user=user, approve=False, note=body.note if body else None)
    db.commit()
    return p
