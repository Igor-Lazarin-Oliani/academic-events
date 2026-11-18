"""API dos agentes. Chat e ocorrências aceitam ?stream=true (Server-Sent Events): cada passo da
trajetória (model.call, tool.call, guardrail, review...) é enviado ao vivo, e o resultado no fim."""

import contextvars
import json
import queue
import threading
from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from app.agentic.agents.operations import run_operations
from app.agentic.agents.participant import run_participant
from app.agentic.models import AgentRun, AgentStep, Conversation, ConversationMessage
from app.agentic.tools.ops_tools import OPS_TOOLS
from app.agentic.tools.participant_tools import PARTICIPANT_TOOLS
from app.core import database
from app.core.database import get_db
from app.core.deps import ensure_can_manage_event, get_current_user, managed_event_ids, require_roles
from app.core.errors import DomainError, Forbidden, NotFound
from app.modules.auth.models import User
from app.modules.events.service import get_event

router = APIRouter(tags=["agents"])


class ChatIn(BaseModel):
    event_id: str
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


class IncidentIn(BaseModel):
    event_id: str
    incident: str = Field(min_length=10, max_length=3000)


def _sse(job: Callable[[DbSession, list], dict]) -> StreamingResponse:
    q: queue.Queue = queue.Queue()

    def worker():
        db = database.session_factory()()
        try:
            q.put(("result", job(db, [lambda ev: q.put(("step", ev))])))
        except DomainError as exc:
            q.put(("error", exc.to_dict()))
        except Exception as exc:  # noqa: BLE001
            q.put(("error", {"code": "internal_error", "message": str(exc)[:300]}))
        finally:
            db.close()
            q.put(None)

    threading.Thread(target=contextvars.copy_context().run, args=(worker,), daemon=True).start()

    def gen():
        while True:
            try:
                item = q.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if item is None:
                return
            kind, data = item
            yield f"event: {kind}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/assistant/chat")
def chat(body: ChatIn, stream: bool = False, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    event = get_event(db, body.event_id)
    if not stream:
        return run_participant(db, user=user, event=event, message=body.message, conversation_id=body.conversation_id)
    user_id, event_id = user.id, event.id
    return _sse(lambda s, listeners: run_participant(s, user=s.get(User, user_id), event=get_event(s, event_id), message=body.message,
                                                     conversation_id=body.conversation_id, listeners=listeners))


@router.get("/assistant/conversations")
def my_conversations(event_id: str | None = None, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    stmt = select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.created_at.desc()).limit(20)
    if event_id:
        stmt = stmt.where(Conversation.event_id == event_id)
    return [{"id": c.id, "event_id": c.event_id, "created_at": c.created_at} for c in db.scalars(stmt)]


@router.get("/assistant/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise NotFound("Conversation not found")
    if conv.user_id != user.id:
        raise Forbidden("Conversation belongs to another user")
    rows = db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conv.id).order_by(ConversationMessage.created_at))
    return [{"id": m.id, "role": m.role, "content": m.content, "payload": m.payload, "run_id": m.run_id, "created_at": m.created_at} for m in rows]


@router.post("/operations/incidents")
def incident(body: IncidentIn, stream: bool = False, user: User = Depends(require_roles("organizer", "admin")), db: DbSession = Depends(get_db)):
    event = get_event(db, body.event_id)
    ensure_can_manage_event(db, user, event.id)  # roteamento determinístico por papel e escopo
    if not stream:
        return run_operations(db, user=user, event=event, incident=body.incident)
    user_id, event_id = user.id, event.id
    return _sse(lambda s, listeners: run_operations(s, user=s.get(User, user_id), event=get_event(s, event_id), incident=body.incident, listeners=listeners))


# ---- trajetórias e métricas ----------------------------------------------------------------
class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent: str
    user_id: str | None
    event_id: str | None
    conversation_id: str | None
    correlation_id: str | None
    status: str
    current_node: str | None
    input: str
    model_calls: int
    tool_calls: int
    tokens_in: int
    tokens_out: int
    started_at: datetime
    ended_at: datetime | None
    error: str | None


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    seq: int
    type: str
    name: str
    agent: str | None
    status: str
    input: dict | None
    output: dict | None
    duration_ms: int | None
    tokens_in: int | None
    tokens_out: int | None
    created_at: datetime


class RunDetailOut(RunOut):
    state: dict
    output: dict | None
    steps: list[StepOut]


def _visible(db: DbSession, user: User, stmt):
    if user.role == "admin":
        return stmt
    ids = managed_event_ids(db, user) if user.role in ("organizer", "staff") else set()
    return stmt.where(or_(AgentRun.user_id == user.id, AgentRun.event_id.in_(ids or {"-"})))


@router.get("/runs", response_model=list[RunOut])
def list_runs(agent: str | None = None, status: str | None = None, event_id: str | None = None, limit: int = 50,
              user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    stmt = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(min(limit, 200))
    for col, val in ((AgentRun.agent, agent), (AgentRun.status, status), (AgentRun.event_id, event_id)):
        if val:
            stmt = stmt.where(col == val)
    return list(db.scalars(_visible(db, user, stmt)))


@router.get("/runs/stats")
def run_stats(event_id: str | None = None, user: User = Depends(require_roles("organizer", "admin")), db: DbSession = Depends(get_db)):
    base = _visible(db, user, select(AgentRun))
    if event_id:
        base = base.where(AgentRun.event_id == event_id)
    runs = list(db.scalars(base))
    ids = [r.id for r in runs]
    tool_errors = db.scalar(select(func.count(AgentStep.id)).where(AgentStep.run_id.in_(ids), AgentStep.type == "tool.result", AgentStep.status != "ok")) if ids else 0
    tool_results = db.scalar(select(func.count(AgentStep.id)).where(AgentStep.run_id.in_(ids), AgentStep.type == "tool.result")) if ids else 0
    guardrails = dict(db.execute(select(AgentStep.name, func.count(AgentStep.id)).where(AgentStep.run_id.in_(ids), AgentStep.type == "guardrail",
                                                                                      AgentStep.status.in_(["blocked", "rejected", "flagged"])).group_by(AgentStep.name)).all()) if ids else {}
    durations = sorted((r.ended_at - r.started_at).total_seconds() for r in runs if r.ended_at)
    by = {}
    for r in runs:
        by.setdefault(r.agent, {}).setdefault(r.status, 0)
        by[r.agent][r.status] += 1

    def pct(p):
        return round(durations[min(len(durations) - 1, int(p * len(durations)))], 2) if durations else None

    return {"runs": len(runs), "by_agent_status": by, "tokens_in": sum(r.tokens_in for r in runs), "tokens_out": sum(r.tokens_out for r in runs),
            "model_calls": sum(r.model_calls for r in runs), "tool_calls": sum(r.tool_calls for r in runs),
            "tool_error_rate": round(tool_errors / tool_results, 3) if tool_results else 0, "guardrail_events": guardrails,
            "latency_s": {"p50": pct(0.5), "p95": pct(0.95)}}


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def get_run(run_id: str, user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    run = db.scalar(_visible(db, user, select(AgentRun).where(AgentRun.id == run_id)))
    if not run:
        raise NotFound("Run not found")
    return run


@router.get("/agents")
def agents_catalog():
    """Ficha de cada agente: objetivo, tools (com nível L0–L3) e critérios de parada (para a UI e a defesa)."""
    def tools(ts):
        return [{"name": t.name, "level": t.level, "effect": t.effect, "description": t.description, "roles": sorted(t.roles),
                 "parameters": t.spec().parameters} for t in ts]

    return [
        {"name": "participant", "title": "Assistente do Participante", "pattern": "agente único + tools",
         "goal": "Resolver dúvidas e solicitações do participante sobre o evento, o regulamento e os próprios ingressos.",
         "decides": "quais fontes consultar, se responde, se abstém, se propõe ação ou escala", "tools": tools(PARTICIPANT_TOOLS),
         "stop": ["final_answer validada (schema + grounding)", "max_steps", "max_tokens", "timeout", "modelo indisponível (modo degradado)"]},
        {"name": "operations", "title": "Agente de Operações", "pattern": "grafo de estados + evaluator-optimizer + human-in-the-loop",
         "goal": "Transformar uma ocorrência em um plano de ação verificável para aprovação da comissão.",
         "decides": "o elemento afetado, as alternativas e os passos do plano; redige o comunicado", "tools": tools(OPS_TOOLS),
         "stop": ["plano proposto (pausa em HUMAN_APPROVAL)", "need_info / no_action / refusal", "≤ 2 revisões", "budget", "modelo indisponível"]},
        {"name": "reviewer", "title": "Agente Revisor", "pattern": "evaluator (checagens determinísticas + LLM com schema)",
         "goal": "Garantir que o comunicado é fiel aos fatos validados, completo, claro e sem dados pessoais.",
         "decides": "aprovar ou devolver com problemas objetivos", "tools": [],
         "stop": ["parecer emitido (uma chamada)"]},
    ]


@router.get("/evals/latest")
def latest_evals(_: User = Depends(require_roles("organizer", "admin"))):
    """Último relatório da suíte de evals (gerado por `python /evals/run.py`)."""
    import os
    from pathlib import Path

    path = Path(os.environ.get("EVALS_DIR", "/evals/reports")) / "latest.json"
    if not path.exists():
        raise NotFound("No eval report yet. Run: docker compose exec backend python /evals/run.py")
    return json.loads(path.read_text(encoding="utf-8"))
