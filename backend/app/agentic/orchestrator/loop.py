"""Loop agêntico: perceber -> decidir -> agir -> observar -> continuar?

O orquestrador é software convencional: ele controla quais tools o modelo vê, por quanto tempo
roda (budget), quando para (final_answer validado, budget, modelo indisponível) e registra tudo."""

import json
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, ValidationError

from app.agentic.ports.model import Message, ModelPort, ModelUnavailable, ToolCall, ToolResult, ToolSpec
from app.agentic.orchestrator.resilience import Budget, BudgetExceeded
from app.agentic.tools.base import ToolContext, to_gemini_schema
from app.agentic.tools.gateway import ToolGateway
from app.agentic.tracing import RunRecorder, Timer

FINAL_TOOL = "final_answer"


@dataclass
class AgentSpec:
    name: str
    system_prompt: str
    tools: list[str]
    final_model: type[BaseModel]
    final_description: str = "Entrega a resposta final estruturada e encerra a tarefa."
    max_steps: int = 8
    max_tokens: int = 60_000
    timeout_seconds: float = 120.0
    tier: str = "default"
    # validação extra da resposta final (guardrail de saída); devolve a lista de problemas
    final_check: Callable[[dict, ToolContext], list[str]] | None = None
    # tools que encerram o trabalho: depois de uma execução bem-sucedida, o modelo só vê final_answer
    terminal_tools: frozenset[str] = frozenset()


@dataclass
class LoopOutcome:
    status: str  # DONE | BUDGET_EXCEEDED | DEGRADED | FAILED
    final: dict | None = None
    reason: str | None = None
    messages: list[Message] = field(default_factory=list)
    budget: dict | None = None
    # resultados do último turno (inclui o da final_answer): quem continuar a conversa
    # precisa devolvê-los ao modelo, porque toda functionCall exige uma functionResponse
    last_results: list[ToolResult] = field(default_factory=list)


class AgentLoop:
    def __init__(self, model: ModelPort, gateway: ToolGateway):
        self.model = model
        self.gateway = gateway

    def run(self, spec: AgentSpec, ctx: ToolContext, user_text: str | None, *, recorder: RunRecorder, history: list[Message] | None = None) -> LoopOutcome:
        messages = list(history or []) + ([Message(role="user", text=user_text)] if user_text is not None else [])
        final_spec = ToolSpec(FINAL_TOOL, spec.final_description, to_gemini_schema(spec.final_model.model_json_schema()))
        tools = self.gateway.specs(spec.tools) + [final_spec]
        allowed = set(spec.tools)
        budget = Budget(max_steps=spec.max_steps, max_tokens=spec.max_tokens, timeout_seconds=spec.timeout_seconds)
        no_tool_turns = 0
        seen_calls: set[str] = set()
        unavailable: set[str] = set()   # tools que responderam 503 nesta execução
        unavailable_turns = 0

        while True:
            try:
                budget.check()
            except BudgetExceeded as exc:
                recorder.step("guardrail", "budget_exceeded", agent=spec.name, status="blocked", output=budget.snapshot())
                return LoopOutcome("BUDGET_EXCEEDED", reason=exc.reason, messages=messages, budget=budget.snapshot())

            try:
                with Timer() as t:
                    resp = self.model.generate(system=spec.system_prompt, messages=messages, tools=tools, force_tool=True, tier=spec.tier)
            except ModelUnavailable as exc:
                recorder.step("model.call", getattr(self.model, "name", "model"), agent=spec.name, status="unavailable", output={"error": str(exc), "attempts": exc.attempts})
                return LoopOutcome("DEGRADED", reason=str(exc), messages=messages, budget=budget.snapshot())
            except Exception as exc:  # erro não recuperável do provedor
                recorder.step("model.call", getattr(self.model, "name", "model"), agent=spec.name, status="error", output={"error": str(exc)[:500]})
                return LoopOutcome("FAILED", reason=str(exc), messages=messages, budget=budget.snapshot())

            budget.consume(resp.usage.input_tokens + resp.usage.output_tokens)
            recorder.step(
                "model.call", resp.model, agent=spec.name, duration_ms=t.ms, tokens_in=resp.usage.input_tokens, tokens_out=resp.usage.output_tokens,
                output={"text": (resp.text or "")[:1000], "tool_calls": [{"name": c.name, "args": c.args} for c in resp.tool_calls],
                        "attempts": resp.attempts, "budget": budget.snapshot()},
            )
            messages.append(Message(role="model", text=resp.text, tool_calls=resp.tool_calls, raw=resp.raw))

            if not resp.tool_calls:
                no_tool_turns += 1
                if no_tool_turns >= 2:
                    return LoopOutcome("FAILED", reason="model did not call final_answer", messages=messages, budget=budget.snapshot())
                messages.append(Message(role="user", text=f"Responda chamando a ferramenta {FINAL_TOOL}."))
                continue

            results, final = [], None
            for call in resp.tool_calls:
                if call.name == FINAL_TOOL:
                    content, final_ok = self._final(spec, ctx, call, recorder)
                    if final_ok is not None:
                        final = final_ok
                    results.append(ToolResult(call, content))
                else:
                    key = f"{call.name}:{json.dumps(call.args, sort_keys=True, default=str)}"
                    if key in seen_calls:  # guarda de loop: mesma tool com os mesmos argumentos
                        recorder.step("guardrail", "duplicate_call", agent=spec.name, status="blocked", input={"tool": call.name, "args": call.args})
                        results.append(ToolResult(call, {"ok": False, "error": {"code": "duplicate_call", "message": "Esta chamada já foi feita; use o resultado anterior."}}))
                        continue
                    seen_calls.add(key)
                    if call.name in unavailable:  # não insiste numa tool que já está fora do ar
                        recorder.step("guardrail", "tool_unavailable_skip", agent=spec.name, status="blocked", input={"tool": call.name})
                        results.append(ToolResult(call, {"ok": False, "error": {"code": "unavailable", "message": f"'{call.name}' continua indisponível nesta conversa. Não tente de novo: informe o usuário e ofereça encaminhar à comissão."}}))
                        continue
                    result = self.gateway.execute(call.name, call.args, ctx, allowed=allowed, recorder=recorder)
                    if not result.get("ok") and result.get("error", {}).get("code") == "unavailable":
                        unavailable.add(call.name)
                    results.append(ToolResult(call, result))
                    if call.name in spec.terminal_tools and result.get("ok") and tools[-1] is final_spec and len(tools) > 1:
                        tools = [final_spec]  # o orquestrador, não o modelo, decide que é hora de encerrar
                        recorder.step("guardrail", "terminal_tool", agent=spec.name, status="passed", input={"tool": call.name, "next": FINAL_TOOL})
            if final is not None:
                return LoopOutcome("DONE", final=final, messages=messages, budget=budget.snapshot(), last_results=results)
            data_results = [r for r in results if r.call.name != FINAL_TOOL]
            if data_results and all(r.content.get("error", {}).get("code") == "unavailable" for r in data_results):
                unavailable_turns += 1
                if unavailable_turns >= 2 and len(tools) > 1:
                    # degradação controlada: sem fontes, o modelo só pode encerrar (ou escalar) com honestidade
                    keep = [t for t in tools if t.name in ("escalate_to_organizer",) and t.name in allowed]
                    tools = keep + [final_spec]
                    recorder.step("guardrail", "tools_unavailable", agent=spec.name, status="flagged", input={"unavailable": sorted(unavailable), "next": [t.name for t in tools]})
            else:
                unavailable_turns = 0
            messages.append(Message(role="tool", tool_results=results))

    def _final(self, spec: AgentSpec, ctx: ToolContext, call: ToolCall, recorder: RunRecorder) -> tuple[dict, dict | None]:
        try:
            final = spec.final_model.model_validate(call.args).model_dump(mode="json")
        except ValidationError as exc:
            errors = [{"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]} for e in exc.errors()]
            recorder.step("guardrail", "final_schema", agent=spec.name, status="rejected", output={"errors": errors})
            return {"ok": False, "error": {"code": "invalid_final_answer", "details": errors}}, None
        problems = spec.final_check(final, ctx) if spec.final_check else []
        if problems:
            recorder.step("guardrail", "output_grounding", agent=spec.name, status="rejected", input=final, output={"problems": problems})
            return {"ok": False, "error": {"code": "final_answer_rejected", "problems": problems,
                                           "hint": "Corrija usando apenas dados devolvidos pelas ferramentas, ou responda com kind=abstain."}}, None
        recorder.step("guardrail", "output_grounding", agent=spec.name, status="passed")
        return {"ok": True}, final
