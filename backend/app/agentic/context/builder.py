"""Context Builder: monta o contrato de contexto de cada execução (objeto estruturado, não texto solto).

Só entra o necessário para a próxima decisão: escopo, datas do evento, políticas e budget.
Conhecimento (regulamento) e dados (programação, ingressos) são recuperados SOB DEMANDA pelas tools."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.knowledge.search import list_documents
from app.modules.events.models import Event, Room

TZ = ZoneInfo("America/Campo_Grande")
WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def local(dt: datetime) -> datetime:
    return dt.astimezone(TZ)


def fmt_iso(dt: datetime) -> str:
    return local(dt).isoformat(timespec="minutes")


def fmt_label(start: datetime, end: datetime) -> str:
    s, e = local(start), local(end)
    return f"{WEEKDAYS[s.weekday()]} {s:%d/%m} {s:%H}h{s:%M}–{e:%H}h{e:%M}"


def event_days(event: Event) -> list[dict]:
    days, d = [], local(event.start_at).date()
    while d <= local(event.end_at).date():
        days.append({"date": d.isoformat(), "weekday": WEEKDAYS[d.weekday()], "label": f"{d:%d/%m}"})
        d += timedelta(days=1)
    return days


def _base(db: DbSession, event: Event, user, task: str) -> dict:
    return {
        "task": task,
        "now": datetime.now(TZ).isoformat(timespec="minutes"),
        "scope": {"event_id": event.id, "event_slug": event.slug, "role": user.role, "user_first_name": user.name.split()[0]},
        "event": {
            "title": event.title,
            "location": event.location,
            "period": f"{local(event.start_at):%d/%m/%Y} a {local(event.end_at):%d/%m/%Y}",
            "days": event_days(event),
            "timezone": "America/Campo_Grande (UTC-04:00)",
            "max_minicursos_per_participant": event.max_minicursos_per_participant,
        },
        "knowledge_sources": [{"source_id": d.source_id, "title": d.title, "version": d.version, "trust": d.trust} for d in list_documents(db, event.id)],
    }


def participant_context(db: DbSession, event: Event, user, *, budget: dict) -> dict:
    ctx = _base(db, event, user, "atender o participante sobre o evento, a programação, o regulamento e os PRÓPRIOS ingressos")
    ctx["retrieval"] = {"methods": ["keyword (full-text)", "dados estruturados (programação, ingressos do usuário)"]}
    ctx["policy"] = {"read": "automático (L0)", "abrir_chamado": "automático com log (L1)",
                     "cancelar_ou_trocar_ingresso": "somente proposta; o próprio usuário confirma na tela (L2)",
                     "dados_de_outros_participantes": "proibido", "alterar_programacao": "proibido"}
    ctx["budget"] = budget
    return ctx


def operations_context(db: DbSession, event: Event, user, *, budget: dict) -> dict:
    ctx = _base(db, event, user, "transformar uma ocorrência em um plano de ação verificável para aprovação da comissão")
    ctx["rooms"] = [{"name": r.name, "capacity": r.capacity, "available": r.available, "resources": r.resources}
                    for r in db.scalars(select(Room).where(Room.event_id == event.id).order_by(Room.name))]
    ctx["retrieval"] = {"methods": ["graph (impacto)", "keyword (regulamento)", "disponibilidade (salas e horários)"]}
    ctx["policy"] = {"read": "automático (L0)", "plano": "o sistema valida (dry-run), o Revisor confere e um organizador aprova (L3)",
                     "dados_pessoais": "o agente vê só contagens, nunca nomes ou e-mails"}
    ctx["budget"] = budget
    return ctx


def render(ctx: dict) -> str:
    return "## Contrato de contexto desta execução (JSON)\n```json\n" + json.dumps(ctx, ensure_ascii=False, indent=1) + "\n```"
