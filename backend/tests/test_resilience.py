"""Confiabilidade do ModelPort: retry, fallback de modelos, circuit breaker e budget (sem rede)."""

import httpx
import pytest

from app.agentic.adapters.gemini import GeminiAdapter
from app.agentic.orchestrator.resilience import Budget, BudgetExceeded, CircuitBreaker, with_retry
from app.agentic.ports.model import Message, ModelError, ModelUnavailable, ToolCall, ToolResult
from app.core.config import Settings

OK = {"candidates": [{"content": {"parts": [{"functionCall": {"name": "x", "args": {"a": 1}, "id": "c1"}, "thoughtSignature": "sig"}]}, "finishReason": "STOP"}],
      "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}


def adapter(handler) -> tuple[GeminiAdapter, list]:
    seen = []

    def wrapped(request: httpx.Request):
        seen.append(request.url.path.split("/")[-1].split(":")[0])
        return handler(request, len(seen))

    settings = Settings(gemini_api_key="k", gemini_model="primary", gemini_model_light="light", gemini_fallback_models="backup", model_max_retries=1)
    return GeminiAdapter(settings, client=httpx.Client(transport=httpx.MockTransport(wrapped)), sleep=lambda s: None), seen


def gen(a):
    return a.generate(system="s", messages=[Message(role="user", text="oi")])


def test_falls_back_to_next_model_on_503():
    a, seen = adapter(lambda req, n: httpx.Response(503, json={"error": {"message": "high demand"}}) if "primary" in req.url.path else httpx.Response(200, json=OK))
    r = gen(a)
    assert r.model == "light" and seen == ["primary", "primary", "light"]  # 1 retry no primário, depois o próximo da cadeia
    assert r.tool_calls[0].args == {"a": 1} and r.usage.input_tokens == 10
    assert [x["outcome"] for x in r.attempts] == ["error", "error", "ok"]


def test_timeout_skips_retry_and_goes_to_fallback():
    def h(req, n):
        if "primary" in req.url.path:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json=OK)

    a, seen = adapter(h)
    assert gen(a).model == "light" and seen == ["primary", "light"]


def test_quota_429_skips_to_next_model_without_retry():
    a, seen = adapter(lambda req, n: httpx.Response(429, json={"error": {"message": "quota"}}) if "light" in req.url.path else httpx.Response(200, json=OK))
    r = a.generate(system="s", messages=[Message(role="user", text="oi")], tier="light")
    assert r.model == "backup" and seen == ["light", "backup"]  # cadeia leve: light -> backup -> primary


def test_client_error_is_not_retried():
    a, seen = adapter(lambda req, n: httpx.Response(400, json={"error": {"message": "bad"}}))
    with pytest.raises(ModelUnavailable) as exc:
        gen(a)
    assert seen == ["primary", "light", "backup"] and len(exc.value.attempts) == 3


def test_missing_key_is_unavailable():
    a = GeminiAdapter(Settings(gemini_api_key=""))
    with pytest.raises(ModelUnavailable):
        gen(a)


def test_raw_parts_are_preserved_in_history():
    """O thoughtSignature do Gemini precisa voltar intacto na próxima chamada."""
    a, _ = adapter(lambda req, n: httpx.Response(200, json=OK))
    r = gen(a)
    content = GeminiAdapter._content(Message(role="model", tool_calls=r.tool_calls, raw=r.raw))
    assert content["parts"][0]["thoughtSignature"] == "sig"
    call = ToolCall(id="c1", name="x", args={})
    tool_msg = GeminiAdapter._content(Message(role="tool", tool_results=[ToolResult(call, {"ok": True})]))
    assert tool_msg["parts"][0]["functionResponse"] == {"name": "x", "id": "c1", "response": {"ok": True}}


def test_circuit_breaker_opens_and_half_opens():
    now = [0.0]
    cb = CircuitBreaker("m", failure_threshold=2, reset_seconds=10, clock=lambda: now[0])

    def boom():
        raise ModelError("x", retryable=True, status=503)

    for _ in range(2):
        with pytest.raises(ModelError):
            cb.call(boom)
    assert cb.state == "open"
    with pytest.raises(ModelUnavailable):
        cb.call(lambda: "never called")
    now[0] = 11
    assert cb.state == "half_open"
    assert cb.call(lambda: "ok") == "ok" and cb.state == "closed"


def test_retry_only_retryable():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ModelError("429", retryable=True, status=429)
        return "ok"

    assert with_retry(flaky, retries=2, sleep=lambda s: None) == "ok" and len(calls) == 3
    calls.clear()
    with pytest.raises(ModelError):
        with_retry(lambda: (_ for _ in ()).throw(ModelError("400", retryable=False)), retries=5, sleep=lambda s: None)


def test_budget_limits():
    b = Budget(max_steps=2, max_tokens=100)
    b.check()
    b.consume(10)
    b.consume(10)
    with pytest.raises(BudgetExceeded, match="max_steps"):
        b.check()
    b2 = Budget(max_steps=10, max_tokens=100)
    b2.consume(150)
    with pytest.raises(BudgetExceeded, match="max_tokens"):
        b2.check()
