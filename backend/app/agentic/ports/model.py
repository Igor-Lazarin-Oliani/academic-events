"""ModelPort: o que o orquestrador precisa de um LLM, independentemente do provedor."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema dos argumentos


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ToolResult:
    call: ToolCall
    content: dict  # sempre estruturado: {"ok": bool, "data"|"error": ...}


@dataclass
class Message:
    role: str  # "user" | "model" | "tool"
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    raw: Any = None  # partes originais do provedor (ex.: thoughtSignature do Gemini)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ModelResponse:
    text: str | None
    tool_calls: list[ToolCall]
    usage: Usage
    model: str
    raw: Any = None
    finish_reason: str | None = None
    attempts: list[dict] = field(default_factory=list)  # retries e fallbacks (vão para o trace)


class ModelError(Exception):
    """Falha do provedor. retryable indica se vale tentar de novo (429, 5xx, timeout)."""

    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None, attempts: list[dict] | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.attempts = attempts or []


class ModelUnavailable(ModelError):
    """Provedor indisponível depois dos retries/fallbacks, ou circuito aberto."""


class ModelPort(Protocol):
    name: str

    def generate(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        force_tool: bool = False,
        response_schema: dict | None = None,
        tier: str = "default",  # "default" | "light"
        temperature: float = 0.0,
    ) -> ModelResponse: ...
