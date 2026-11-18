"""Runner de evals de comportamento (modelo REAL), em banco próprio, recriado e semeado a cada execução.

Uso (dentro do contêiner):  python /evals/run.py [--only P01,O01] [--category injecao] [--delay 3] [--no-reset]
Saída: /evals/reports/<data>.json, latest.json e latest.md.

Princípio da disciplina: não testar o texto exato; testar invariantes, efeitos, fontes citadas e
resultados observáveis (com oráculos SQL quando possível)."""

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/app")

import yaml  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core import database  # noqa: E402

ROOT = Path(__file__).parent
EVAL_URL = os.environ.get("EVAL_DATABASE_URL", os.environ.get("DATABASE_URL", "").rsplit("/", 1)[0] + "/academic_events_eval")
EVENT_SLUG = "semana-facom-2026"
DEFAULT_USER = "participante@exemplo.com"


def norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(c))


def ensure_db():
    import psycopg
    from sqlalchemy.engine import make_url

    u = make_url(EVAL_URL)
    with psycopg.connect(host=u.host, port=u.port or 5432, user=u.username, password=u.password, dbname="postgres", autocommit=True) as conn:
        if not conn.execute("select 1 from pg_database where datname=%s", (u.database,)).fetchone():
            conn.execute(f'create database "{u.database}"')
    database.configure(EVAL_URL)


def snapshot(db) -> str:
    from app.modules.events.models import Room, Session
    from app.modules.tickets.models import Ticket

    rows = [("t", t.id, t.status) for t in db.scalars(select(Ticket).order_by(Ticket.id))]
    rows += [("s", s.id, s.start_at.isoformat(), s.room_id, s.status) for s in db.scalars(select(Session).order_by(Session.id))]
    rows += [("r", r.id, r.available) for r in db.scalars(select(Room).order_by(Room.id))]
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()


def run_case(db, case: dict) -> dict:
    from app.agentic.agents.operations import run_operations
    from app.agentic.agents.participant import run_participant
    from app.agentic.agents import reviewer
    from app.agentic.models import AgentStep
    from app.agentic.providers import get_model
    from app.agentic.tracing import RunRecorder
    from app.core.errors import Forbidden
    from app.modules.approvals.models import ActionProposal
    from app.modules.approvals.service import dry_run_plan
    from app.modules.auth.models import User
    from app.modules.events.service import get_event
    from app.modules.tickets.models import Ticket, TicketStatus

    event = get_event(db, EVENT_SLUG)
    user = db.scalar(select(User).where(User.email == case.get("user", DEFAULT_USER)))
    message, subst = case.get("message", ""), {}
    setup = case.get("setup") or {}
    if "other_ticket_of" in setup:
        other = db.scalar(select(User).where(User.email == setup["other_ticket_of"]))
        t = db.scalar(select(Ticket).where(Ticket.user_id == other.id, Ticket.status != TicketStatus.CANCELLED))
        subst = {"other_ticket": t.ticket_code, "other_session_title": t.session.title, "other_session_code": t.session.code}
    for k, v in subst.items():
        message = message.replace("{" + k + "}", v)

    before = snapshot(db)
    started = time.time()
    agent = case.get("agent", "participant")
    out: dict = {}
    if agent == "participant":
        r = run_participant(db, user=user, event=event, message=message, simulate_unavailable=set(setup.get("simulate_unavailable", [])))
        out = {"status": r["status"], "kind": r["kind"], "answer": r["answer"], "evidence": r["evidence"], "proposals": [p["id"] for p in r["proposals"]], "run_id": r["run_id"]}
    elif agent == "operations":
        try:
            r = run_operations(db, user=user, event=event, incident=message)
            draft = r.get("draft") or {}
            out = {"status": r["status"], "kind": draft.get("kind"), "answer": draft.get("diagnosis", "") + "\n" + json.dumps(draft.get("communication"), ensure_ascii=False),
                   "proposals": [r["proposal"]["id"]] if r.get("proposal") else [], "run_id": r["run_id"], "review": r.get("review"), "revisions": r.get("revisions")}
        except Forbidden as exc:
            out = {"status": "FORBIDDEN", "kind": None, "answer": exc.message, "proposals": [], "run_id": None}
    elif agent == "reviewer":
        plan = case["plan"]
        validation = dry_run_plan(db, event.id, [{"type": "RESCHEDULE_SESSION", **plan}], actor=user or db.scalar(select(User).where(User.role == "organizer")))
        rec = RunRecorder(agent="reviewer", user_id=None, event_id=event.id, input_text=json.dumps(case["communication"], ensure_ascii=False))
        rv = reviewer.review(db, event_id=event.id, communication=case["communication"], validation=validation, model=get_model(), recorder=rec)
        rec.finish("DONE", output={"approved": rv["approved"], "issues": rv["issues"]})
        rec.close()
        out = {"status": "DONE", "kind": None, "answer": "", "proposals": [], "run_id": rec.run_id, "review": rv}
    out["latency_s"] = round(time.time() - started, 2)
    db.expire_all()
    out["side_effects"] = snapshot(db) != before

    trace = [(s.type, s.name, s.status) for s in db.scalars(select(AgentStep).where(AgentStep.run_id == out["run_id"]).order_by(AgentStep.seq))] if out["run_id"] else []
    out["tools_called"] = [n for t, n, _ in trace if t == "tool.call"]
    out["guardrails"] = [n for t, n, st in trace if t == "guardrail" and st != "passed"]
    out["model_calls"] = sum(1 for t, *_ in trace if t == "model.call")
    proposals = list(db.scalars(select(ActionProposal).where(ActionProposal.id.in_(out["proposals"])))) if out["proposals"] else []
    return evaluate(db, case, out, subst, proposals)


def evaluate(db, case, out, subst, proposals) -> dict:
    from app.modules.events.models import Session
    from app.modules.tickets.models import Ticket, TicketStatus

    exp, checks = case.get("expect", {}), []

    def check(name, ok, detail=""):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    ans = norm(out.get("answer", ""))
    cited = {f"{e['source_id']}#{e.get('section', '')}" for e in out.get("evidence", [])}
    sources = {e["source_id"] for e in out.get("evidence", [])}
    if "status" in exp:
        check("status", out["status"] == exp["status"], out["status"])
    if "status_in" in exp:
        check("status_in", out["status"] in exp["status_in"], out["status"])
    if "kind_in" in exp:
        check("kind_in", out["kind"] in exp["kind_in"], out["kind"])
    if "evidence_any" in exp:
        check("evidence_any", cited & set(exp["evidence_any"]), sorted(cited))
    if "evidence_source_any" in exp:
        check("evidence_source_any", sources & set(exp["evidence_source_any"]), sorted(sources))
    if "evidence_none_from" in exp:
        check("evidence_none_from", not (sources & set(exp["evidence_none_from"])), sorted(sources))
    if "answer_contains_any" in exp:
        check("answer_contains_any", any(norm(x) in ans for x in exp["answer_contains_any"]), out.get("answer", "")[:200])
    if "answer_contains_all" in exp:
        check("answer_contains_all", all(norm(x) in ans for x in exp["answer_contains_all"]), out.get("answer", "")[:200])
    if "answer_not_contains" in exp:
        bad = [x for x in exp["answer_not_contains"] if norm(x.format(**subst) if "{" in x else x) in ans]
        check("answer_not_contains", not bad, bad)
    if "proposals" in exp:
        check("proposals", len(out["proposals"]) == exp["proposals"], len(out["proposals"]))
    if "tools_called" in exp:
        check("tools_called", all(t in out["tools_called"] for t in exp["tools_called"]), out["tools_called"])
    if "guardrails" in exp:
        check("guardrails", all(g in out["guardrails"] for g in exp["guardrails"]), out["guardrails"])
    if exp.get("no_side_effects"):
        check("no_side_effects", not out["side_effects"])
    if "review_approved" in exp:
        check("review_approved", out["review"]["approved"] == exp["review_approved"], out["review"].get("issues"))
    p = proposals[0] if proposals else None
    steps = (p.payload.get("steps", []) if p else [])
    if "plan_step_types_any" in exp:
        check("plan_step_types_any", any(s["type"] in exp["plan_step_types_any"] for s in steps), [s["type"] for s in steps])
    if "plan_sessions" in exp:
        touched = {s.get("session_code") for s in steps}
        check("plan_sessions", set(exp["plan_sessions"]) <= touched, sorted(x for x in touched if x))
    if exp.get("affected_oracle"):
        codes = [s["session_code"] for s in steps if s.get("session_code")]
        ids = list(db.scalars(select(Session.id).where(Session.code.in_(codes), Session.event_id == p.event_id))) if p else []
        oracle = db.scalar(select(func.count(func.distinct(Ticket.user_id))).where(Ticket.session_id.in_(ids), Ticket.status != TicketStatus.CANCELLED)) if ids else -1
        got = (p.impact or {}).get("recipients") if p else None
        check("affected_oracle", got == oracle, {"plan": got, "sql": oracle})
    passed = all(c["passed"] for c in checks)
    return {"id": case["id"], "category": case["category"], "agent": case.get("agent", "participant"), "passed": passed, "checks": checks,
            **{k: out.get(k) for k in ("status", "kind", "latency_s", "model_calls", "tools_called", "guardrails", "run_id", "revisions")},
            "answer": (out.get("answer") or "")[:600]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--category", default="")
    ap.add_argument("--delay", type=float, default=float(os.environ.get("EVAL_DELAY", "3")))
    ap.add_argument("--no-reset", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    ensure_db()
    import app.models  # noqa: F401
    from app.seed.seed import seed

    if not args.no_reset:
        database.Base.metadata.drop_all(database.engine())
    database.create_all()
    with database.session_factory()() as db:
        seed(db)

    cases = [c for f in sorted((ROOT / "cases").glob("*.yaml")) for c in yaml.safe_load(f.read_text(encoding="utf-8"))]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only.split(",")]
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]

    results = []
    for i, case in enumerate(cases):
        with database.session_factory()() as db:
            try:
                r = run_case(db, case)
            except Exception as exc:  # noqa: BLE001
                r = {"id": case["id"], "category": case["category"], "agent": case.get("agent", "participant"), "passed": False,
                     "checks": [{"check": "exception", "passed": False, "detail": f"{exc}"}], "error": traceback.format_exc()[-1500:]}
        results.append(r)
        flag = "PASS" if r["passed"] else "FAIL"
        failed = [c["check"] for c in r["checks"] if not c["passed"]]
        print(f"[{flag}] {r['id']:<4} {r['category']:<24} status={r.get('status')} kind={r.get('kind')} {r.get('latency_s')}s {'' if r['passed'] else failed}", flush=True)
        if i < len(cases) - 1:
            time.sleep(args.delay)

    by_cat = {}
    for r in results:
        c = by_cat.setdefault(r["category"], {"passed": 0, "total": 0})
        c["total"] += 1
        c["passed"] += int(r["passed"])
    lat = [r["latency_s"] for r in results if r.get("latency_s") is not None]
    report = {"generated_at": datetime.now().isoformat(timespec="seconds"), "model": {k: os.environ.get(k) for k in ("GEMINI_MODEL", "GEMINI_MODEL_LIGHT", "GEMINI_FALLBACK_MODELS")},
              "total": len(results), "passed": sum(r["passed"] for r in results), "by_category": by_cat,
              "avg_latency_s": round(sum(lat) / len(lat), 2) if lat else None, "results": results}
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    partial = bool(args.only or args.category)  # execuções parciais não substituem o relatório completo
    names = [f"partial-{stamp}.json"] if partial else [f"{stamp}.json", "latest.json"]
    for name in names:
        (out_dir / name).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md = [f"# Relatório de evals ({report['generated_at']})", "", f"**{report['passed']}/{report['total']} casos aprovados** · latência média {report['avg_latency_s']} s", "",
          "| Categoria | Aprovados |", "|---|---|"] + [f"| {k} | {v['passed']}/{v['total']} |" for k, v in by_cat.items()] + ["", "| Caso | Resultado | Status | Kind | Falhas |", "|---|---|---|---|---|"]
    md += [f"| {r['id']} | {'✅' if r['passed'] else '❌'} | {r.get('status')} | {r.get('kind')} | {', '.join(c['check'] for c in r['checks'] if not c['passed'])} |" for r in results]
    (out_dir / "latest.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\n{report['passed']}/{report['total']} aprovados · {by_cat}")


if __name__ == "__main__":
    main()
