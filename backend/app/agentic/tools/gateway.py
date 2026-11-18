"""Tool Gateway: a fronteira de confiança entre o modelo e o sistema.

"O LLM solicita; o sistema autoriza e registra." Toda chamada passa por:
allowlist do agente -> papel do usuário -> validação dos argumentos -> execução com timeout
(statement_timeout do PostgreSQL) num SAVEPOINT -> resultado estruturado -> trace."""

import logging

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError

from app.agentic.tools.base import Tool, ToolContext
from app.agentic.tracing import RunRecorder, Timer
from app.core.config import get_settings
from app.core.errors import DomainError

logger = logging.getLogger("academic_events.tools")


def _err(code: str, message: str, **extra) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, **extra}}


class ToolGateway:
    def __init__(self, tools: list[Tool]):
        self.tools = {t.name: t for t in tools}

    def specs(self, names: list[str]):
        return [self.tools[n].spec() for n in names]

    def execute(self, name: str, args: dict, ctx: ToolContext, *, allowed: set[str], recorder: RunRecorder | None = None) -> dict:
        if recorder:
            recorder.step("tool.call", name, agent=ctx.agent, input=args)
        with Timer() as t:
            result = self._execute(name, args, ctx, allowed, recorder)
        if recorder:
            status = "ok" if result.get("ok") else result["error"]["code"]
            recorder.step("tool.result", name, agent=ctx.agent, status=status, output=result, duration_ms=t.ms)
        return result

    def _execute(self, name, args, ctx: ToolContext, allowed, recorder) -> dict:
        tool = self.tools.get(name)
        if tool is None or name not in allowed:
            self._guardrail(recorder, ctx, "tool_not_allowed", {"tool": name})
            return _err("tool_not_allowed", f"Tool '{name}' is not available to this agent")
        if ctx.user.role not in tool.roles:
            self._guardrail(recorder, ctx, "role_denied", {"tool": name, "role": ctx.user.role})
            return _err("forbidden", f"Role '{ctx.user.role}' cannot use '{name}'", status=403)
        try:
            parsed = tool.args_model.model_validate(args or {})
        except ValidationError as exc:
            errors = [{"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]} for e in exc.errors()]
            return _err("invalid_arguments", "Fix the arguments and try again", details=errors)
        if name in ctx.simulate_unavailable:
            return _err("unavailable", f"Tool '{name}' is temporarily unavailable", status=503)

        db = ctx.db
        nested = db.begin_nested()
        try:
            db.execute(text(f"SET LOCAL statement_timeout = {int(get_settings().tool_timeout_seconds * 1000)}"))
            data = tool.handler(ctx, parsed)
            if isinstance(data, dict) and data.get("guardrail"):
                self._guardrail(recorder, ctx, "injection_redacted", data["guardrail"], status="flagged")
            nested.commit()
            db.commit()  # efeitos L1/L2 (chamado, proposta) persistem mesmo se a run falhar depois
            return {"ok": True, "data": data}
        except DomainError as exc:
            nested.rollback()
            db.commit()
            if exc.status_code == 403:
                self._guardrail(recorder, ctx, "access_denied", {"tool": name, "code": exc.code})
            return {"ok": False, "error": exc.to_dict()}
        except (OperationalError, DBAPIError) as exc:
            nested.rollback()
            db.rollback()
            if "statement timeout" in str(exc).lower() or "canceling statement" in str(exc).lower():
                return _err("timeout", f"Tool '{name}' exceeded {get_settings().tool_timeout_seconds}s", status=504)
            logger.exception("tool %s database error", name)
            return _err("internal_error", "Database error while executing the tool", status=500)
        except Exception:
            nested.rollback()
            db.rollback()
            logger.exception("tool %s failed", name)
            return _err("internal_error", f"Unexpected error in '{name}'", status=500)

    @staticmethod
    def _guardrail(recorder, ctx, rule: str, detail: dict, status: str = "blocked") -> None:
        if recorder:
            recorder.step("guardrail", rule, agent=ctx.agent, status=status, input=detail)
