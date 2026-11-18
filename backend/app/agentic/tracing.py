"""RunRecorder: StatePort + TracePort em PostgreSQL.

Usa uma sessão de banco PRÓPRIA e faz commit a cada passo, para que a trajetória fique visível
ao vivo (SSE) e sobreviva mesmo se a execução falhar no meio."""

import json
import re
import time
from datetime import date, datetime
from typing import Callable

from sqlalchemy import update

from app.agentic.models import AgentRun, AgentStep
from app.core.database import session_factory, utcnow

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _safe(value):
    """Serializável em JSON e com e-mails mascarados (dados pessoais fora do trace)."""
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return str(o)

    raw = json.dumps(value, default=default, ensure_ascii=False)
    raw = _EMAIL.sub(lambda m: m.group(0)[0] + "***@" + m.group(0).split("@")[1], raw)
    if len(raw) > 20_000:
        return {"truncated": True, "preview": raw[:20_000]}
    return json.loads(raw)


class RunRecorder:
    def __init__(self, *, agent: str, user_id: str | None, event_id: str | None, input_text: str, correlation_id: str | None = None,
                 conversation_id: str | None = None, run_id: str | None = None):
        self._db = session_factory()()
        self._seq = 0
        self.listeners: list[Callable[[dict], None]] = []
        if run_id:  # retomando uma execução existente
            self.run = self._db.get(AgentRun, run_id)
            self._seq = len(self.run.steps)
        else:
            self.run = AgentRun(agent=agent, user_id=user_id, event_id=event_id, input=input_text, correlation_id=correlation_id, conversation_id=conversation_id)
            self._db.add(self.run)
            self._db.commit()
        self.run_id = self.run.id

    def step(self, type_: str, name: str = "", *, agent: str | None = None, status: str = "ok", input=None, output=None,
             duration_ms: int | None = None, tokens_in: int | None = None, tokens_out: int | None = None) -> dict:
        self._seq += 1
        s = AgentStep(run_id=self.run_id, seq=self._seq, type=type_, name=name, agent=agent, status=status,
                      input=_safe(input) if input is not None else None, output=_safe(output) if output is not None else None,
                      duration_ms=duration_ms, tokens_in=tokens_in, tokens_out=tokens_out)
        self._db.add(s)
        counters = {}
        if type_ == "model.call":
            counters = {"model_calls": AgentRun.model_calls + 1, "tokens_in": AgentRun.tokens_in + (tokens_in or 0), "tokens_out": AgentRun.tokens_out + (tokens_out or 0)}
        elif type_ == "tool.call":
            counters = {"tool_calls": AgentRun.tool_calls + 1}
        if counters:
            self._db.execute(update(AgentRun).where(AgentRun.id == self.run_id).values(**counters))
        self._db.commit()
        event = {"run_id": self.run_id, "seq": s.seq, "type": type_, "name": name, "agent": agent, "status": status, "input": s.input, "output": s.output,
                 "duration_ms": duration_ms, "tokens_in": tokens_in, "tokens_out": tokens_out, "at": s.created_at.isoformat()}
        for fn in self.listeners:
            try:
                fn(event)
            except Exception:  # um ouvinte com problema não derruba a execução
                pass
        return event

    def checkpoint(self, node: str, state: dict) -> None:
        self._db.execute(update(AgentRun).where(AgentRun.id == self.run_id).values(current_node=node, state=_safe(state)))
        self._db.commit()

    def finish(self, status: str, *, output: dict | None = None, error: str | None = None) -> None:
        self._db.execute(update(AgentRun).where(AgentRun.id == self.run_id).values(status=status, output=_safe(output) if output else None, error=error, ended_at=utcnow()))
        self._db.commit()

    def pause(self, status: str, *, output: dict | None = None) -> None:
        self._db.execute(update(AgentRun).where(AgentRun.id == self.run_id).values(status=status, output=_safe(output) if output else None))
        self._db.commit()

    def set_status(self, status: str) -> None:
        self._db.execute(update(AgentRun).where(AgentRun.id == self.run_id).values(status=status))
        self._db.commit()

    def close(self) -> None:
        self._db.close()


class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = int((time.perf_counter() - self.start) * 1000)
