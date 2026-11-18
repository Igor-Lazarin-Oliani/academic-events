"""FakeModel: modelo roteirizado para testes determinísticos (sem custo, sem rede).

Cada item do roteiro é uma resposta, uma exceção ou uma função (messages, tools) -> resposta.
Helpers call() e text() deixam os testes legíveis."""

import itertools
from typing import Callable

from app.agentic.ports.model import Message, ModelError, ModelResponse, ToolCall, ToolSpec, Usage

_ids = itertools.count(1)


def call(name: str, **args) -> ModelResponse:
    return ModelResponse(text=None, tool_calls=[ToolCall(id=f"fake_{next(_ids)}", name=name, args=args)], usage=Usage(100, 20), model="fake")


def calls(*pairs: tuple[str, dict]) -> ModelResponse:
    return ModelResponse(text=None, tool_calls=[ToolCall(id=f"fake_{next(_ids)}", name=n, args=a) for n, a in pairs], usage=Usage(100, 30), model="fake")


def text(content: str) -> ModelResponse:
    return ModelResponse(text=content, tool_calls=[], usage=Usage(100, 40), model="fake")


class FakeModel:
    name = "fake"

    def __init__(self, script: list | Callable | None = None):
        self.script = script if callable(script) else list(script or [])
        self.requests: list[dict] = []

    def generate(self, *, system, messages: list[Message], tools: list[ToolSpec] | None = None, force_tool=False,
                 response_schema=None, tier="default", temperature=0.0) -> ModelResponse:
        self.requests.append({"system": system, "messages": list(messages), "tools": [t.name for t in tools or []],
                              "force_tool": force_tool, "schema": response_schema, "tier": tier})
        if callable(self.script):
            item = self.script(messages, tools)
        else:
            if not self.script:
                raise ModelError("FakeModel script exhausted", retryable=False)
            item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
