"""Tools do Assistente do Participante. Escopo: o evento atual e os ingressos DO USUÁRIO AUTENTICADO
(ctx.user). Nenhuma tool recebe user_id: o modelo não consegue pedir dados de outra pessoa."""

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agentic.context.builder import fmt_iso, fmt_label
from app.agentic.tools.base import Tool, ToolContext
from app.agentic.tools.common import SEARCH_TOOL
from app.core.errors import Conflict, DomainError, NotFound
from app.knowledge.text import normalize
from app.modules.approvals.models import ActionProposal, ProposalKind, ProposalStatus
from app.modules.approvals.service import create_proposal
from app.modules.events.models import Session
from app.modules.events.service import get_session, list_sessions
from app.modules.notifications.service import open_support_request
from app.modules.tickets import service as tickets
from app.modules.tickets.models import TicketStatus

PARTICIPANT_ROLES = frozenset({"participant", "staff", "organizer", "admin"})


def session_view(s: Session, *, spots: bool = True) -> dict:
    v = {"code": s.code, "title": s.title, "kind": s.kind, "track": s.track, "when": fmt_label(s.start_at, s.end_at),
         "start_at": fmt_iso(s.start_at), "end_at": fmt_iso(s.end_at), "room": s.room.name if s.room else None,
         "speakers": [sp.name for sp in s.speakers], "workload_hours": s.workload_hours, "status": s.status}
    if spots:
        v["available_spots"] = s.available_spots
        v["max_capacity"] = s.max_capacity
    return v


def ticket_view(t) -> dict:
    return {"ticket_code": t.ticket_code, "status": t.status, "session": session_view(t.session, spots=False),
            "checked_in_at": fmt_iso(t.checked_in_at) if t.checked_in_at else None}


# --- programação -------------------------------------------------------------------------------
class ScheduleArgs(BaseModel):
    day: str | None = Field(default=None, description="Data AAAA-MM-DD (opcional)")
    kind: Literal["PALESTRA", "MINICURSO", "MESA_REDONDA", "WORKSHOP", "ABERTURA"] | None = Field(default=None, description="Tipo de sessão (opcional)")
    text: str | None = Field(default=None, description="Filtro por palavra no título, trilha ou palestrante (opcional)")


def get_event_schedule(ctx: ToolContext, a: ScheduleArgs) -> dict:
    sessions = list_sessions(ctx.db, ctx.event_id, day=a.day, kind=a.kind)
    if a.text:
        words = normalize(a.text).split()
        sessions = [s for s in sessions if all(w in normalize(f"{s.code} {s.title} {s.track} {' '.join(sp.name for sp in s.speakers)}") for w in words)]
    for s in sessions:
        ctx.add_evidence({"source_id": "PROGRAMACAO", "section": s.code, "title": s.title})
    return {"sessions": [session_view(s) for s in sessions], "count": len(sessions),
            "evidence_hint": "Cite source_id=PROGRAMACAO e section=<código da sessão>."}


# --- ingressos do usuário --------------------------------------------------------------------
class NoArgs(BaseModel):
    pass


def list_my_tickets(ctx: ToolContext, _: NoArgs) -> dict:
    items = tickets.list_tickets(ctx.db, user_id=ctx.user.id, event_id=ctx.event_id)
    for t in items:
        ctx.add_evidence({"source_id": "MEUS_INGRESSOS", "section": t.ticket_code})
    active = [t for t in items if t.status != TicketStatus.CANCELLED]
    return {"tickets": [ticket_view(t) for t in items], "active": len(active),
            "evidence_hint": "Cite source_id=MEUS_INGRESSOS e section=<ticket_code>."}


class TicketArgs(BaseModel):
    ticket_code: str = Field(description="Código do ingresso, formato EVT-AAAA-XXXXXX")


def get_ticket_status(ctx: ToolContext, a: TicketArgs) -> dict:
    t = tickets.get_own_ticket(ctx.db, ctx.user, a.ticket_code)  # 403 se for de outra pessoa
    ctx.add_evidence({"source_id": "MEUS_INGRESSOS", "section": t.ticket_code})
    return ticket_view(t)


# --- propostas (L2) --------------------------------------------------------------------------
def _pending_same(ctx: ToolContext, kind: str, payload: dict) -> ActionProposal | None:
    for p in ctx.db.scalars(select(ActionProposal).where(ActionProposal.requested_by == ctx.user.id, ActionProposal.kind == kind,
                                                        ActionProposal.status == ProposalStatus.PENDING)):
        if all(p.payload.get(k) == v for k, v in payload.items() if k != "reason"):
            return p
    return None


def _proposal_out(ctx: ToolContext, p: ActionProposal, reused: bool) -> dict:
    if p.id not in ctx.proposals_created:
        ctx.proposals_created.append(p.id)
    return {"proposal_id": p.id, "status": p.status, "title": p.title, "reused_existing": reused,
            "next_step": f"Agora chame final_answer com kind=action_proposed e proposal_ids=['{p.id}'], pedindo ao usuário que confirme no cartão exibido na tela. Nada foi alterado ainda."}


class CancelArgs(BaseModel):
    ticket_code: str = Field(description="Código do ingresso a cancelar")
    reason: str = Field(default="", max_length=300, description="Motivo informado pelo usuário (opcional)")


def propose_ticket_cancellation(ctx: ToolContext, a: CancelArgs) -> dict:
    t = tickets.get_own_ticket(ctx.db, ctx.user, a.ticket_code)
    if t.status == TicketStatus.CANCELLED:
        raise Conflict("Ticket already cancelled", code="already_cancelled")
    if t.status == TicketStatus.CHECKED_IN:
        raise Conflict("Checked-in tickets cannot be cancelled (regulamento 3.1)", code="already_checked_in")
    payload = {"ticket_id": t.id, "reason": a.reason}
    existing = _pending_same(ctx, ProposalKind.CANCEL_TICKET, payload)
    if existing:
        return _proposal_out(ctx, existing, True)
    p = create_proposal(ctx.db, kind=ProposalKind.CANCEL_TICKET, requested_by=ctx.user, event_id=ctx.event_id, run_id=ctx.run_id,
                        title=f"Cancelar inscrição em {t.session.code} · {t.session.title}",
                        summary=f"Ingresso {t.ticket_code} ({fmt_label(t.session.start_at, t.session.end_at)}). A vaga será liberada.",
                        payload=payload, impact={"ticket_code": t.ticket_code, "session": session_view(t.session, spots=False)})
    return _proposal_out(ctx, p, False)


class SwapArgs(BaseModel):
    ticket_code: str = Field(description="Código do ingresso atual")
    to_session_code: str = Field(description="Código da sessão de destino, ex.: S08")


def propose_session_swap(ctx: ToolContext, a: SwapArgs) -> dict:
    t = tickets.get_own_ticket(ctx.db, ctx.user, a.ticket_code)
    target = get_session(ctx.db, a.to_session_code.upper(), event_id=ctx.event_id)
    # valida a troca de verdade (vaga, conflito, limite) e desfaz: o usuário só vê propostas viáveis
    nested = ctx.db.begin_nested()
    try:
        tickets.swap_session(ctx.db, user=ctx.user, ticket=t, to_session_id=target.id, source="agent")
    except DomainError:
        nested.rollback()
        ctx.db.expire_all()
        raise
    nested.rollback()
    ctx.db.expire_all()
    t = tickets.get_own_ticket(ctx.db, ctx.user, a.ticket_code)
    target = get_session(ctx.db, target.id)
    payload = {"ticket_id": t.id, "to_session_id": target.id}
    existing = _pending_same(ctx, ProposalKind.SWAP_SESSION, payload)
    if existing:
        return _proposal_out(ctx, existing, True)
    p = create_proposal(ctx.db, kind=ProposalKind.SWAP_SESSION, requested_by=ctx.user, event_id=ctx.event_id, run_id=ctx.run_id,
                        title=f"Trocar {t.session.code} por {target.code}",
                        summary=f"Sai de {t.session.title} e entra em {target.title} ({fmt_label(target.start_at, target.end_at)}).",
                        payload=payload, impact={"from": session_view(t.session, spots=False), "to": session_view(target)})
    return _proposal_out(ctx, p, False)


class EscalateArgs(BaseModel):
    summary: str = Field(min_length=10, max_length=1500, description="Resumo da dúvida/pedido para a comissão, sem dados sensíveis")


def escalate_to_organizer(ctx: ToolContext, a: EscalateArgs) -> dict:
    req = open_support_request(ctx.db, user=ctx.user, event_id=ctx.event_id, summary=a.summary, run_id=ctx.run_id)
    ctx.support_requests.append(req.id)
    return {"support_request_id": req.id, "status": req.status, "sla": "A comissão responde em até 2 dias úteis (regulamento 8)."}


PARTICIPANT_TOOLS = [
    SEARCH_TOOL,
    Tool("get_event_schedule", "Lista a programação do evento (sessões, horários, salas, palestrantes, vagas e carga horária).", ScheduleArgs, get_event_schedule),
    Tool("list_my_tickets", "Lista os ingressos do usuário autenticado neste evento.", NoArgs, list_my_tickets),
    Tool("get_ticket_status", "Consulta um ingresso do usuário autenticado pelo código. Ingressos de outras pessoas são negados.", TicketArgs, get_ticket_status),
    Tool("propose_ticket_cancellation", "Cria uma SOLICITAÇÃO de cancelamento do ingresso do usuário; ele confirma na tela.", CancelArgs,
         propose_ticket_cancellation, level="L2", effect="cria proposta pendente; nada é cancelado sem confirmação do usuário"),
    Tool("propose_session_swap", "Cria uma SOLICITAÇÃO de troca de sessão, já validada (vaga, conflito, limite); o usuário confirma na tela.", SwapArgs,
         propose_session_swap, level="L2", effect="cria proposta pendente; nada é trocado sem confirmação do usuário"),
    Tool("escalate_to_organizer", "Abre um chamado para a comissão organizadora quando a dúvida não pode ser resolvida aqui.", EscalateArgs,
         escalate_to_organizer, level="L1", effect="abre chamado (reversível)"),
]
PARTICIPANT_TOOL_NAMES = [t.name for t in PARTICIPANT_TOOLS]
