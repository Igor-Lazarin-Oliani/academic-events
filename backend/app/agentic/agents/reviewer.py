"""Agente Revisor (evaluator do padrão evaluator-optimizer).

1) Checagens DETERMINÍSTICAS: toda data, horário, sala e sessão citados no comunicado batem
   com os fatos do dry-run; os novos valores aparecem; tamanho adequado.
2) Checagem pelo LLM (modelo leve, saída JSON com schema): fidelidade, completude, clareza, privacidade.
Se o LLM estiver indisponível, vale só a parte determinística (e isso fica registrado)."""

import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.agentic.context.builder import fmt_label, local
from app.agentic.ports.model import Message, ModelError, ModelPort
from app.agentic.tracing import RunRecorder, Timer
from app.knowledge.search import search
from app.knowledge.text import normalize
from app.modules.events.models import Room, Session

PROMPT = (Path(__file__).parent.parent / "prompts" / "reviewer.md").read_text(encoding="utf-8")
SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["approved", "issues", "suggestions"],
}
_TIME = re.compile(r"\b(\d{1,2})\s*(?:h|:)\s*(\d{2})?\b(?!\s*horas)", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/\d{2,4})?\b")
_CODE = re.compile(r"\b([A-Z]\d{2})\b")


def facts_from_validation(db: DbSession, event_id: str, validation: dict) -> dict:
    """Fatos verificáveis extraídos do dry-run: sessões tocadas, antes/depois, salas, destinatários."""
    changes, sessions, rooms, times, dates, must_mention = [], set(), set(), set(), set(), []
    def add_dt(iso: str):
        dt = local(datetime.fromisoformat(iso))
        times.add((dt.hour, dt.minute))
        dates.add((dt.day, dt.month))
        return dt

    recipients = 0
    for r in validation.get("results", []):
        t = r["type"]
        if t == "NOTIFY_PARTICIPANTS":
            recipients = r["recipients"]
            continue
        if "session" in r:
            sessions.add(r["session"])
        if t == "RESCHEDULE_SESSION":
            b, a = r["before"], r["after"]
            add_dt(b["start_at"]); add_dt(b["end_at"])
            new_start, new_end = add_dt(a["start_at"]), add_dt(a["end_at"])
            rooms.update(x for x in (b["room"], a["room"]) if x)
            must_mention.append({"what": "novo horário", "time": (new_start.hour, new_start.minute), "date": (new_start.day, new_start.month)})
            if a["room"] and a["room"] != b["room"]:
                must_mention.append({"what": "nova sala", "room": a["room"]})
            changes.append({"session": r["session"], "before": f"{fmt_label(datetime.fromisoformat(b['start_at']), datetime.fromisoformat(b['end_at']))}, {b['room']}",
                            "after": f"{fmt_label(new_start, new_end)}, {a['room']}"})
        elif t == "CHANGE_ROOM":
            rooms.update(x for x in (r["from_room"], r["to_room"]) if x)
            must_mention.append({"what": "nova sala", "room": r["to_room"]})
            changes.append({"session": r["session"], "before": r["from_room"], "after": r["to_room"]})
        elif t == "CANCEL_SESSION":
            changes.append({"session": r["session"], "after": "CANCELADA", "tickets_cancelled": r["tickets_cancelled"]})
        elif t == "MARK_ROOM_UNAVAILABLE":
            rooms.add(r["room"])
            changes.append({"room": r["room"], "after": "indisponível"})
    # horários e datas originais das sessões tocadas também podem ser citados
    for s in db.scalars(select(Session).where(Session.event_id == event_id, Session.code.in_(sessions))):
        add_dt(s.start_at.isoformat()); add_dt(s.end_at.isoformat())
        if s.room:
            rooms.add(s.room.name)
        changes_titles = {c.get("session") for c in changes}
        if s.code in changes_titles:
            for c in changes:
                if c.get("session") == s.code:
                    c["title"] = s.title
    return {"changes": changes, "sessions": sorted(sessions), "rooms": sorted(rooms), "times": sorted(times), "dates": sorted(dates),
            "must_mention": must_mention, "recipients": recipients}


def deterministic_check(db: DbSession, event_id: str, communication: dict | None, facts: dict) -> list[str]:
    if not communication:
        return ["O plano não tem comunicado aos inscritos."]
    title, body = communication.get("title", ""), communication.get("body", "")
    issues = []
    if not 3 <= len(title) <= 120:
        issues.append("O título deve ter entre 3 e 120 caracteres.")
    if not 40 <= len(body) <= 1500:
        issues.append("O corpo deve ter entre 40 e 1500 caracteres.")
    text = f"{title}\n{body}"
    times = {tuple(t) for t in facts["times"]}
    dates = {tuple(d) for d in facts["dates"]}
    for h, m in _TIME.findall(text):
        hm = (int(h), int(m or 0))
        if 0 <= hm[0] <= 23 and hm not in times:
            issues.append(f"Horário {hm[0]:02d}h{hm[1]:02d} citado não corresponde a nenhum horário (antigo ou novo) das sessões alteradas.")
    for d, mth in _DATE.findall(text):
        if (int(d), int(mth)) not in dates:
            issues.append(f"Data {int(d):02d}/{int(mth):02d} citada não corresponde às datas das sessões alteradas.")
    all_codes = set(db.scalars(select(Session.code).where(Session.event_id == event_id)))
    for code in set(_CODE.findall(text)):
        if code in all_codes and code not in facts["sessions"]:
            issues.append(f"A sessão {code} é citada, mas não faz parte do plano.")
    norm = normalize(text)
    for room in db.scalars(select(Room.name).where(Room.event_id == event_id)):
        if normalize(room) in norm and room not in facts["rooms"]:
            issues.append(f"A sala {room} é citada, mas não está envolvida na mudança.")
    found_times = {(int(h), int(m or 0)) for h, m in _TIME.findall(text)}
    found_dates = {(int(d), int(mth)) for d, mth in _DATE.findall(text)}
    for need in facts["must_mention"]:
        if "time" in need and (tuple(need["time"]) not in found_times or tuple(need["date"]) not in found_dates):
            h, m = need["time"]
            d, mth = need["date"]
            issues.append(f"O comunicado não informa o novo horário ({d:02d}/{mth:02d}, {h:02d}h{m:02d}).")
        if "room" in need and normalize(need["room"]) not in norm:
            issues.append(f"O comunicado não informa a nova sala ({need['room']}).")
    return list(dict.fromkeys(issues))


def review(db: DbSession, *, event_id: str, communication: dict | None, validation: dict, model: ModelPort, recorder: RunRecorder) -> dict:
    facts = facts_from_validation(db, event_id, validation)
    det = deterministic_check(db, event_id, communication, facts)
    recorder.step("review", "deterministic", agent="reviewer", status="passed" if not det else "issues", input={"communication": communication}, output={"facts": facts, "issues": det})
    rule = search(db, event_id=event_id, query="alteracoes programacao comunicacao inscritos", limit=1)
    llm: dict
    if communication:
        payload = {"comunicado": communication, "fatos_verificados": {k: facts[k] for k in ("changes", "recipients")},
                   "regra_do_regulamento": {"source_id": rule[0]["evidence"]["source_id"], "section": rule[0]["section"], "content": rule[0]["content"]} if rule else None}
        try:
            with Timer() as t:
                resp = model.generate(system=PROMPT, messages=[Message(role="user", text=json.dumps(payload, ensure_ascii=False))], response_schema=SCHEMA, tier="light")
            recorder.step("model.call", resp.model, agent="reviewer", duration_ms=t.ms, tokens_in=resp.usage.input_tokens, tokens_out=resp.usage.output_tokens,
                          output={"text": (resp.text or "")[:1500], "attempts": resp.attempts})
            llm = json.loads(resp.text or "{}")
            llm = {"approved": bool(llm.get("approved")), "issues": list(llm.get("issues", [])), "suggestions": list(llm.get("suggestions", []))}
        except (ModelError, ValueError) as exc:
            llm = {"skipped": True, "reason": str(exc)[:300], "approved": True, "issues": [], "suggestions": []}
            recorder.step("review", "llm_skipped", agent="reviewer", status="skipped", output=llm)
    else:
        llm = {"approved": False, "issues": [], "suggestions": []}
    approved = not det and llm["approved"]
    result = {"approved": approved, "deterministic_issues": det, "llm": llm, "issues": det + llm.get("issues", []),
              "suggestions": llm.get("suggestions", []), "facts": facts}
    recorder.step("review", "verdict", agent="reviewer", status="approved" if approved else "rejected", output={k: result[k] for k in ("approved", "issues", "suggestions")})
    return result
