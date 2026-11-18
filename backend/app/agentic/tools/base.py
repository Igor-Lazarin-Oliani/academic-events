"""Tool = contrato explícito: nome, descrição do efeito, argumentos tipados (Pydantic),
nível de autonomia (L0–L3), papéis autorizados e saída estruturada."""

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app.agentic.ports.model import ToolSpec

LEVELS = {
    "L0": "leitura: automático",
    "L1": "reversível: automático + log",
    "L2": "efeito no sistema: confirmação do próprio usuário fora do chat",
    "L3": "crítico/coletivo: aprovação de um organizador na Central de Aprovações",
}


@dataclass
class ToolContext:
    db: DbSession
    user: Any  # User autenticado (o escopo vem daqui, nunca dos argumentos do modelo)
    agent: str
    run_id: str
    event_id: str | None
    correlation_id: str | None = None
    evidence_seen: dict[str, dict] = field(default_factory=dict)  # chave "source_id#section" -> evidência
    proposals_created: list[str] = field(default_factory=list)
    support_requests: list[str] = field(default_factory=list)
    simulate_unavailable: set[str] = field(default_factory=set)  # evals: simula tool fora do ar
    facts: dict = field(default_factory=dict)  # dados estruturados que as tools produziram (para o Revisor)

    def add_evidence(self, ev: dict) -> None:
        key = f"{ev.get('source_id')}#{ev.get('section', '')}"
        self.evidence_seen[key] = ev


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], Any]
    level: str = "L0"
    roles: frozenset[str] = frozenset({"participant", "staff", "organizer", "admin"})
    effect: str = "nenhum (somente leitura)"

    def spec(self) -> ToolSpec:
        desc = f"{self.description} [nível {self.level}; efeito: {self.effect}]"
        return ToolSpec(name=self.name, description=desc, parameters=to_gemini_schema(self.args_model.model_json_schema()))


_ALLOWED_KEYS = {"type", "description", "enum", "properties", "required", "items", "minimum", "maximum", "minItems", "maxItems", "nullable", "format"}


def to_gemini_schema(schema: dict) -> dict:
    """JSON Schema do Pydantic -> subconjunto OpenAPI aceito pelo function calling (sem $ref/anyOf/title)."""
    defs = schema.get("$defs", {})

    def clean(node: dict) -> dict:
        if "$ref" in node:
            node = defs[node["$ref"].split("/")[-1]]
        if "anyOf" in node:  # Optional[X] -> X nullable
            options = [o for o in node["anyOf"] if o.get("type") != "null"]
            merged = {**clean(options[0]), "nullable": True} if options else {"type": "string"}
            if "description" in node:
                merged["description"] = node["description"]
            return merged
        out = {k: v for k, v in node.items() if k in _ALLOWED_KEYS}
        if out.get("format") not in (None, "date-time", "enum"):
            out.pop("format")
        if "properties" in out:
            out["properties"] = {k: clean(v) for k, v in out["properties"].items()}
        if "items" in out:
            out["items"] = clean(out["items"])
        if "const" in node:
            out["type"], out["enum"] = "string", [node["const"]]
        return out

    result = clean(schema)
    result.setdefault("type", "object")
    if result["type"] == "object":
        result.setdefault("properties", {})
    return result
