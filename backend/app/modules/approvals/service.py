"""Human-in-the-loop. O agente chama create_*; humanos chamam decide() por uma rota que NÃO é uma tool."""

from pydantic import ValidationError
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session as DbSession

from app.core.database import utcnow
from app.core.deps import can_manage_event, managed_event_ids
from app.core.errors import Conflict, DomainError, Forbidden, NotFound
from app.core.pagination import split_values, text_filter
from app.modules.activity.service import record
from app.modules.approvals.models import ActionProposal, ProposalKind, ProposalStatus
from app.modules.approvals.plan_steps import apply_step, parse_steps
from app.modules.auth.models import User
from app.modules.events.models import Session
from app.modules.tickets import service as tickets


def create_proposal(
    db: DbSession,
    *,
    kind: str,
    requested_by: User,
    title: str,
    summary: str = "",
    payload: dict,
    event_id: str | None,
    impact: dict | None = None,
    communication: dict | None = None,
    review: dict | None = None,
    run_id: str | None = None,
) -> ActionProposal:
    level = "L3" if kind == ProposalKind.ACTION_PLAN else "L2"
    p = ActionProposal(kind=kind, level=level, requested_by=requested_by.id, event_id=event_id, title=title, summary=summary,
                       payload=payload, impact=impact or {}, communication=communication, review=review, run_id=run_id)
    db.add(p)
    db.flush()
    record(db, entity_type="proposal", entity_id=p.id, action="proposal.created", source="agent" if run_id else "api",
           actor=requested_by, message=title, payload={"kind": kind, "level": level, "run_id": run_id})
    return p


def dry_run_plan(db: DbSession, event_id: str, steps: list[dict], actor) -> dict:
    """Valida o plano aplicando os passos dentro de um SAVEPOINT e desfazendo tudo depois.
    Devolve o impacto calculado pelo backend (não pelo modelo)."""
    try:
        parsed = parse_steps(steps)
    except ValidationError as exc:
        return {"valid": False, "errors": [{"step": e["loc"][0] if e["loc"] else None, "message": e["msg"]} for e in exc.errors()]}
    results, errors = [], []
    nested = db.begin_nested()
    try:
        for i, step in enumerate(parsed):
            try:
                results.append({"step": i, "type": step.type, **apply_step(db, event_id, step, proposal_id="dry-run", actor=actor)})
                db.flush()
            except DomainError as exc:
                errors.append({"step": i, "type": step.type, "message": exc.message, "code": exc.code})
                break
    finally:
        nested.rollback()
    db.expire_all()
    return {"valid": not errors, "errors": errors, "results": results}


def decide(db: DbSession, proposal_id: str, *, user: User, approve: bool, note: str | None = None) -> ActionProposal:
    p = db.scalar(select(ActionProposal).where(ActionProposal.id == proposal_id).with_for_update())
    if not p:
        raise NotFound("Proposal not found")
    authorize_decision(db, p, user)
    if p.status != ProposalStatus.PENDING:
        raise Conflict(f"Proposal is {p.status}", code="proposal_not_pending")  # idempotência: decidir 2x não executa 2x
    p.decided_by, p.decided_at, p.decision_note = user.id, utcnow(), note
    if not approve:
        p.status = ProposalStatus.REJECTED
        record(db, entity_type="proposal", entity_id=p.id, action="proposal.rejected", actor=user, message=note or "")
        _link_run(db, p, user)
        return p
    p.status = ProposalStatus.APPROVED
    record(db, entity_type="proposal", entity_id=p.id, action="proposal.approved", actor=user, message=note or "")
    execute(db, p, actor=user)
    _link_run(db, p, user)
    return p


def _link_run(db: DbSession, p: ActionProposal, user: User) -> None:
    """Fecha o ciclo na trajetória da run que originou a proposta (retomada após HUMAN_APPROVAL)."""
    if not p.run_id:
        return
    from app.agentic.models import AgentRun, AgentStep

    run = db.get(AgentRun, p.run_id)
    if not run:
        return
    seq = (db.scalar(select(func.max(AgentStep.seq)).where(AgentStep.run_id == run.id)) or 0) + 1
    db.add(AgentStep(run_id=run.id, seq=seq, type="approval", name=p.status, agent="human", status=p.status.lower(),
                     input={"proposal_id": p.id, "decided_by_role": user.role, "note": p.decision_note},
                     output={"result": p.result, "error": p.error}))
    if p.kind == ProposalKind.ACTION_PLAN and run.status == "WAITING_APPROVAL":
        run.status = {"EXECUTED": "DONE", "REJECTED": "CANCELLED"}.get(p.status, "FAILED")
        run.current_node = {"EXECUTED": "DONE", "REJECTED": "CANCELLED"}.get(p.status, "FAILED")
        run.ended_at = utcnow()


def authorize_decision(db: DbSession, p: ActionProposal, user: User) -> None:
    if p.level == "L2":
        if p.requested_by != user.id:
            raise Forbidden("Only the participant who requested it can confirm", code="not_owner")
    elif not can_manage_event(db, user, p.event_id) or user.role not in ("organizer", "admin"):
        raise Forbidden("Only an organizer of this event can approve", code="event_out_of_scope")


def execute(db: DbSession, p: ActionProposal, *, actor: User) -> ActionProposal:
    """Tudo ou nada: os passos rodam num SAVEPOINT; se um falhar, nada é aplicado e a proposta fica FAILED."""
    nested = db.begin_nested()
    try:
        result = _run(db, p, actor)
        nested.commit()
        p.status, p.executed_at, p.result, p.error = ProposalStatus.EXECUTED, utcnow(), result, None
        record(db, entity_type="proposal", entity_id=p.id, action="proposal.executed", actor=actor, payload={"result": result})
    except (DomainError, ValidationError) as exc:
        nested.rollback()
        msg = exc.message if isinstance(exc, DomainError) else str(exc)
        p.status, p.error = ProposalStatus.FAILED, msg
        record(db, entity_type="proposal", entity_id=p.id, action="proposal.failed", level="ERROR", actor=actor, message=msg)
    return p


def _run(db: DbSession, p: ActionProposal, actor: User) -> dict:
    owner = db.get(User, p.requested_by)
    if p.kind == ProposalKind.CANCEL_TICKET:
        t = tickets.get_own_ticket(db, owner, p.payload["ticket_id"])
        tickets.cancel_ticket(db, t, actor=owner, reason=p.payload.get("reason", ""), source="agent")
        return {"ticket": t.ticket_code, "status": t.status}
    if p.kind == ProposalKind.SWAP_SESSION:
        t = tickets.get_own_ticket(db, owner, p.payload["ticket_id"])
        new = tickets.swap_session(db, user=owner, ticket=t, to_session_id=p.payload["to_session_id"], source="agent")
        target = db.get(Session, new.session_id)
        return {"cancelled": t.ticket_code, "new_ticket": new.ticket_code, "session": target.code}
    if p.kind == ProposalKind.ACTION_PLAN:
        steps = parse_steps(p.payload["steps"])
        done = []
        for i, step in enumerate(steps):
            done.append({"step": i, "type": step.type, **apply_step(db, p.event_id, step, proposal_id=p.id, actor=actor)})
            db.flush()
        return {"steps": done}
    raise DomainError(f"Unknown proposal kind {p.kind}")


def proposals_query(db: DbSession, *, user: User, status: str | None = None, event_id: str | None = None, kind: str | None = None,
                    q: str | None = None) -> Select:
    """Propostas visíveis ao usuário, filtradas no banco (para paginar corretamente).
    Visibilidade: admin vê tudo; os demais veem as próprias e as L3 dos eventos que gerenciam.
    `status` aceita vários valores separados por vírgula; `q` busca em título e resumo."""
    stmt = select(ActionProposal)
    statuses = split_values(status)
    if statuses:
        stmt = stmt.where(ActionProposal.status.in_(statuses))
    if kind:
        stmt = stmt.where(ActionProposal.kind == kind)
    if event_id:
        stmt = stmt.where(ActionProposal.event_id == event_id)
    cond = text_filter(q, ActionProposal.title, ActionProposal.summary)
    if cond is not None:
        stmt = stmt.where(cond)
    if user.role != "admin":
        managed = (managed_event_ids(db, user) or set()) if user.role in ("organizer", "staff") else set()
        stmt = stmt.where(or_(ActionProposal.requested_by == user.id,
                              and_(ActionProposal.level == "L3", ActionProposal.event_id.in_(managed))))
    return stmt.order_by(ActionProposal.created_at.desc(), ActionProposal.id)


def list_proposals(db: DbSession, *, user: User, status: str | None = None, event_id: str | None = None, kind: str | None = None,
                   limit: int = 200) -> list[ActionProposal]:
    return list(db.scalars(proposals_query(db, user=user, status=status, event_id=event_id, kind=kind).limit(limit)))
