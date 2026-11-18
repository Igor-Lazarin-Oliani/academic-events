"""Tools do Agente de Operações (somente organizador/admin do evento). Todas são leitura (L0):
o plano final não é executado por tool. Ele vira proposta e passa por validação, Revisor e humano."""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.agentic.context.builder import TZ, event_days, fmt_iso, fmt_label, local
from app.agentic.tools.base import Tool, ToolContext
from app.agentic.tools.common import SEARCH_TOOL
from app.core.deps import ensure_can_manage_event
from app.knowledge import graph
from app.modules.approvals.service import dry_run_plan
from app.modules.events.models import Event, Room, Session, SessionStatus
from app.modules.events.service import get_session, list_sessions, room_conflicts, speaker_conflicts
from app.modules.tickets.models import Ticket, TicketStatus
from app.modules.tickets.service import count_active_by_session

OPS_ROLES = frozenset({"organizer", "admin"})


def _scope(ctx: ToolContext) -> None:
    ensure_can_manage_event(ctx.db, ctx.user, ctx.event_id)  # 403 se o organizador não gerencia este evento


def _localize(v: datetime | None) -> datetime | None:
    if v is not None and v.tzinfo is None:
        return v.replace(tzinfo=TZ)
    return v


class NoArgs(BaseModel):
    pass


def get_event_overview(ctx: ToolContext, _: NoArgs) -> dict:
    _scope(ctx)
    sessions = list_sessions(ctx.db, ctx.event_id)
    counts = count_active_by_session(ctx.db, [s.id for s in sessions])
    for s in sessions:
        ctx.add_evidence({"source_id": "PROGRAMACAO", "section": s.code})
    rooms = list(ctx.db.scalars(select(Room).where(Room.event_id == ctx.event_id).order_by(Room.name)))
    return {
        "days": event_days(ctx.db.get(Event, ctx.event_id)),
        "rooms": [{"name": r.name, "capacity": r.capacity, "available": r.available} for r in rooms],
        "sessions": [{"code": s.code, "title": s.title, "kind": s.kind, "when": fmt_label(s.start_at, s.end_at), "start_at": fmt_iso(s.start_at),
                      "end_at": fmt_iso(s.end_at), "room": s.room.name if s.room else None, "speakers": [sp.name for sp in s.speakers],
                      "registrations": counts.get(s.id, 0), "capacity": s.max_capacity, "status": s.status} for s in sessions],
    }


class ImpactArgs(BaseModel):
    node_type: Literal["room", "speaker", "session"] = Field(description="Tipo do elemento afetado")
    key: str = Field(description="Nome da sala (ex.: Sala 105), nome do palestrante ou código da sessão (ex.: S12)")
    start: datetime | None = Field(default=None, description="Início da janela afetada, ISO 8601 com -04:00 (opcional)")
    end: datetime | None = Field(default=None, description="Fim da janela afetada, ISO 8601 com -04:00 (opcional)")

    @field_validator("start", "end")
    @classmethod
    def _tz(cls, v):
        return _localize(v)


def query_impact_graph(ctx: ToolContext, a: ImpactArgs) -> dict:
    _scope(ctx)
    r = graph.impact(ctx.db, ctx.event_id, node_type=a.node_type, key=a.key, start=a.start, end=a.end)
    for s in r["affected_sessions"]:
        s["when"] = fmt_label(datetime.fromisoformat(s["start_at"]), datetime.fromisoformat(s["end_at"]))
        s["start_at"], s["end_at"] = fmt_iso(datetime.fromisoformat(s["start_at"])), fmt_iso(datetime.fromisoformat(s["end_at"]))
        ctx.add_evidence({"source_id": "GRAFO", "section": s["session_code"]})
        s.pop("evidence", None)
    ctx.facts.setdefault("impact", []).append(r)
    return r


class RoomsArgs(BaseModel):
    start_at: datetime = Field(description="Início, ISO 8601 com -04:00")
    end_at: datetime = Field(description="Fim, ISO 8601 com -04:00")
    min_capacity: int = Field(default=1, ge=1, description="Capacidade mínima necessária (ex.: número de inscritos)")

    @field_validator("start_at", "end_at")
    @classmethod
    def _tz(cls, v):
        return _localize(v)


def find_available_rooms(ctx: ToolContext, a: RoomsArgs) -> dict:
    _scope(ctx)
    rooms = ctx.db.scalars(select(Room).where(Room.event_id == ctx.event_id, Room.available.is_(True), Room.capacity >= a.min_capacity).order_by(Room.capacity))
    free = [{"name": r.name, "capacity": r.capacity, "resources": r.resources} for r in rooms if not room_conflicts(ctx.db, r.id, a.start_at, a.end_at)]
    return {"window": fmt_label(a.start_at, a.end_at), "rooms": free}


class SlotsArgs(BaseModel):
    session_code: str = Field(description="Código da sessão a remanejar, ex.: S12")
    day: str | None = Field(default=None, description="Restringe a uma data AAAA-MM-DD (opcional)")
    exclude_current: bool = Field(default=True, description="Ignora o horário atual da sessão")


_STARTS = ["08:00", "10:00", "10:30", "14:00", "16:00", "16:30"]


def find_alternative_slots(ctx: ToolContext, a: SlotsArgs) -> dict:
    """Horários em que o palestrante está livre e existe sala livre que comporta os inscritos;
    ordena pelo número de inscritos que teriam conflito com outra inscrição."""
    _scope(ctx)
    s = get_session(ctx.db, a.session_code.upper(), event_id=ctx.event_id)
    event = ctx.db.get(Event, ctx.event_id)
    duration = s.end_at - s.start_at
    registered = count_active_by_session(ctx.db, [s.id]).get(s.id, 0)
    user_ids = list(ctx.db.scalars(select(Ticket.user_id).where(Ticket.session_id == s.id, Ticket.status != TicketStatus.CANCELLED)))
    others = list(ctx.db.scalars(select(Ticket).where(Ticket.user_id.in_(user_ids), Ticket.session_id != s.id, Ticket.status != TicketStatus.CANCELLED))) if user_ids else []
    sessions_by_id = {x.id: x for x in ctx.db.scalars(select(Session).where(Session.event_id == ctx.event_id))}
    rooms = list(ctx.db.scalars(select(Room).where(Room.event_id == ctx.event_id, Room.available.is_(True), Room.capacity >= max(registered, 1)).order_by(Room.capacity)))
    days = [d["date"] for d in event_days(event) if not a.day or d["date"] == a.day]
    slots = []
    for day in days:
        for hm in _STARTS:
            start = datetime.fromisoformat(f"{day}T{hm}:00").replace(tzinfo=TZ)
            end = start + duration
            if start < event.start_at or end > event.end_at or end.time() > datetime.strptime("18:30", "%H:%M").time():
                continue
            if a.exclude_current and start == local(s.start_at):
                continue
            if start <= datetime.now(TZ):
                continue
            if speaker_conflicts(ctx.db, [sp.id for sp in s.speakers], start, end, exclude_session_id=s.id):
                continue
            free = [r for r in rooms if not room_conflicts(ctx.db, r.id, start, end, exclude_session_id=s.id)]
            if not free:
                continue
            conflicted = {t.user_id for t in others if sessions_by_id[t.session_id].start_at < end and sessions_by_id[t.session_id].end_at > start
                          and sessions_by_id[t.session_id].status != SessionStatus.CANCELLED}
            slots.append({"start_at": fmt_iso(start), "end_at": fmt_iso(end), "when": fmt_label(start, end),
                          "rooms": [{"name": r.name, "capacity": r.capacity} for r in free[:3]],
                          "participants_with_conflict": len(conflicted)})
    slots.sort(key=lambda x: (x["participants_with_conflict"], x["start_at"]))
    ctx.facts.setdefault("slots", {})[s.code] = slots[:8]
    return {"session": {"code": s.code, "title": s.title, "current": fmt_label(s.start_at, s.end_at), "room": s.room.name if s.room else None,
                        "speakers": [sp.name for sp in s.speakers], "registrations": registered},
            "alternatives": slots[:8], "note": "Prefira alternativas com menos participantes em conflito."}


class StepIn(BaseModel):
    """Passo do plano (formato plano, aceito pelo function calling)."""
    type: Literal["CHANGE_ROOM", "RESCHEDULE_SESSION", "CANCEL_SESSION", "MARK_ROOM_UNAVAILABLE"]
    session_code: str | None = Field(default=None, description="Sessão (CHANGE_ROOM, RESCHEDULE_SESSION, CANCEL_SESSION)")
    room_name: str | None = Field(default=None, description="Sala de destino (CHANGE_ROOM, opcional em RESCHEDULE) ou sala indisponível (MARK_ROOM_UNAVAILABLE)")
    start_at: str | None = Field(default=None, description="Novo início ISO 8601 com -04:00 (RESCHEDULE_SESSION)")
    end_at: str | None = Field(default=None, description="Novo fim ISO 8601 com -04:00 (RESCHEDULE_SESSION)")
    reason: str | None = Field(default=None, description="Motivo (CANCEL_SESSION, MARK_ROOM_UNAVAILABLE)")

    def to_step(self) -> dict:
        d = {k: v for k, v in self.model_dump().items() if v is not None}
        if self.type == "CANCEL_SESSION":
            d.setdefault("reason", "alteração aprovada pela comissão")
        if self.type == "MARK_ROOM_UNAVAILABLE":
            d.setdefault("reason", "")
        return d


class ValidateArgs(BaseModel):
    steps: list[StepIn] = Field(min_length=1, description="Passos do plano, em ordem")


def validate_plan(ctx: ToolContext, a: ValidateArgs) -> dict:
    _scope(ctx)
    result = dry_run_plan(ctx.db, ctx.event_id, [s.to_step() for s in a.steps], actor=ctx.user)
    ctx.facts["last_validation"] = result
    return result


OPS_TOOLS = [
    SEARCH_TOOL,
    Tool("get_event_overview", "Visão geral do evento: dias, salas (disponibilidade) e todas as sessões com inscritos.", NoArgs, get_event_overview, roles=OPS_ROLES),
    Tool("query_impact_graph", "Análise de impacto no grafo do evento: sessões ligadas a uma sala, palestrante ou sessão, inscritos afetados e caminho.",
         ImpactArgs, query_impact_graph, roles=OPS_ROLES),
    Tool("find_available_rooms", "Salas livres e disponíveis numa janela de horário, com capacidade mínima.", RoomsArgs, find_available_rooms, roles=OPS_ROLES),
    Tool("find_alternative_slots", "Horários alternativos para uma sessão (palestrante livre + sala livre que comporta os inscritos), com conflitos dos inscritos.",
         SlotsArgs, find_alternative_slots, roles=OPS_ROLES),
    Tool("validate_plan", "Valida um plano aplicando os passos em simulação (dry-run, nada é gravado). Use antes da resposta final.",
         ValidateArgs, validate_plan, roles=OPS_ROLES, effect="nenhum (simulação desfeita)"),
]
OPS_TOOL_NAMES = [t.name for t in OPS_TOOLS]
