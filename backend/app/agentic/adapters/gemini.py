"""Adapter do Gemini (REST generateContent) para o ModelPort.

- function calling nativo; force_tool usa o modo ANY (o modelo PRECISA chamar uma tool);
- as partes originais do modelo (com thoughtSignature) são devolvidas intactas no histórico;
- confiabilidade: timeout por chamada, retry com backoff em 429/5xx, cadeia de fallback de
  modelos e circuit breaker por modelo."""

import time
import uuid

import httpx

from app.agentic.orchestrator.resilience import CircuitBreaker
from app.agentic.ports.model import Message, ModelError, ModelResponse, ModelUnavailable, ToolCall, ToolSpec, Usage
from app.core.config import Settings, get_settings

_RETRYABLE = {429, 500, 502, 503, 504}


class GeminiAdapter:
    name = "gemini"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None, sleep=time.sleep):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=httpx.Timeout(self.settings.model_timeout_seconds, connect=10.0))
        self.breakers: dict[str, CircuitBreaker] = {}
        self._sleep = sleep

    # ---- API pública -------------------------------------------------------------------------
    def generate(self, *, system, messages, tools=None, force_tool=False, response_schema=None, tier="default", temperature=0.0) -> ModelResponse:
        if not self.settings.gemini_api_key:
            raise ModelUnavailable("GEMINI_API_KEY not configured")
        body = self._body(system, messages, tools, force_tool, response_schema)
        attempts: list[dict] = []
        for model in self._chain(tier):
            breaker = self.breakers.setdefault(model, CircuitBreaker(model, failure_threshold=3, reset_seconds=60))
            if breaker.state == "open":
                attempts.append({"model": model, "outcome": "circuit_open"})
                continue
            for attempt in range(self.settings.model_max_retries + 1):
                started = time.monotonic()
                try:
                    data = breaker.call(lambda: self._post(model, body))
                    resp = self._parse(model, data)
                    attempts.append({"model": model, "outcome": "ok", "ms": int((time.monotonic() - started) * 1000)})
                    resp.attempts = attempts
                    return resp
                except ModelError as exc:
                    attempts.append({"model": model, "outcome": "error", "status": exc.status, "error": str(exc)[:200], "ms": int((time.monotonic() - started) * 1000)})
                    # timeout: não insiste no mesmo modelo lento; 429 (cota do free tier): a cota não volta em
                    # segundos. Nos dois casos, vai direto para o próximo modelo da cadeia.
                    if not exc.retryable or exc.status in (None, 429) or attempt >= self.settings.model_max_retries:
                        break
                    self._sleep(min(8.0, 1.0 * (2 ** attempt)))
        raise ModelUnavailable("all Gemini models failed", attempts=attempts)

    # ---- detalhes ---------------------------------------------------------------------------
    def _chain(self, tier: str) -> list[str]:
        if tier == "light":
            chain = [self.settings.gemini_model_light, *self.settings.fallback_models, self.settings.gemini_model]
        else:
            chain = [self.settings.gemini_model, self.settings.gemini_model_light, *self.settings.fallback_models]
        return list(dict.fromkeys(chain))

    def _post(self, model: str, body: dict) -> dict:
        url = f"{self.settings.gemini_base_url}/models/{model}:generateContent"
        try:
            r = self.client.post(url, json=body, headers={"x-goog-api-key": self.settings.gemini_api_key})
        except httpx.TimeoutException as exc:
            raise ModelError(f"timeout calling {model}", retryable=True, status=None) from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"network error: {exc}", retryable=True, status=None) from exc
        if r.status_code != 200:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            raise ModelError(f"{model} HTTP {r.status_code}: {msg[:300]}", retryable=r.status_code in _RETRYABLE, status=r.status_code)
        return r.json()

    def _body(self, system: str, messages: list[Message], tools: list[ToolSpec] | None, force_tool: bool, response_schema: dict | None) -> dict:
        body: dict = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [self._content(m) for m in messages]}
        if tools:
            body["tools"] = [{"functionDeclarations": [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools]}]
            if force_tool:
                body["toolConfig"] = {"functionCallingConfig": {"mode": "ANY"}}
        if response_schema:
            body["generationConfig"] = {"responseMimeType": "application/json", "responseJsonSchema": response_schema}
        return body

    @staticmethod
    def _content(m: Message) -> dict:
        if m.role == "model":
            if m.raw:
                return {"role": "model", "parts": m.raw}
            parts = ([{"text": m.text}] if m.text else []) + [{"functionCall": {"name": c.name, "args": c.args, "id": c.id}} for c in m.tool_calls]
            return {"role": "model", "parts": parts}
        if m.role == "tool":
            return {"role": "user", "parts": [{"functionResponse": {"name": r.call.name, "id": r.call.id, "response": r.content}} for r in m.tool_results]}
        return {"role": "user", "parts": [{"text": m.text or ""}]}

    @staticmethod
    def _parse(model: str, data: dict) -> ModelResponse:
        cands = data.get("candidates") or []
        if not cands:
            reason = data.get("promptFeedback", {}).get("blockReason", "no candidates")
            raise ModelError(f"{model} returned no candidates ({reason})", retryable=False, status=200)
        cand = cands[0]
        parts = cand.get("content", {}).get("parts", []) or []
        texts = [p["text"] for p in parts if "text" in p and not p.get("thought")]
        calls = [
            ToolCall(id=p["functionCall"].get("id") or f"call_{uuid.uuid4().hex[:10]}", name=p["functionCall"]["name"], args=p["functionCall"].get("args") or {})
            for p in parts if "functionCall" in p
        ]
        um = data.get("usageMetadata", {})
        usage = Usage(input_tokens=um.get("promptTokenCount", 0), output_tokens=um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0))
        return ModelResponse(text="".join(texts) or None, tool_calls=calls, usage=usage, model=model, raw=parts, finish_reason=cand.get("finishReason"))
