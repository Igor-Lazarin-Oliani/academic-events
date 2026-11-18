"""Gera docs/contratos-tools.md a partir de GET /agents (a fonte da verdade é o código).
Uso: python scripts/gen_tool_contracts.py [http://localhost:8000]"""
import json
import sys
import urllib.request
from pathlib import Path

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
agents = json.loads(urllib.request.urlopen(base + "/agents").read().decode("utf-8"))
LEVEL = {"L0": "leitura, automático", "L1": "reversível, automático + log", "L2": "proposta; o próprio usuário confirma", "L3": "proposta; organizador aprova"}
out = ["# Contratos das ferramentas (tools)", "",
       "> Gerado automaticamente de `GET /agents` por `scripts/gen_tool_contracts.py`. Não edite à mão.", "",
       "Toda chamada passa pelo **Tool Gateway** (`backend/app/agentic/tools/gateway.py`): allowlist do agente → papel do usuário → validação Pydantic → execução num SAVEPOINT com `statement_timeout` → resultado estruturado → trace.", "",
       "**Formato de resultado (sempre):**", "", "```json", '{"ok": true, "data": { ... }}', '{"ok": false, "error": {"code": "ticket_out_of_scope", "message": "...", "status": 403}}', "```", "",
       "Códigos de erro previsíveis: `tool_not_allowed`, `forbidden` (papel), `invalid_arguments` (com `details` por campo), `unavailable` (503), `timeout` (504), `internal_error` e os erros de domínio (`sold_out`, `time_conflict`, `minicurso_limit`, `ticket_out_of_scope`, `event_out_of_scope`, `already_checked_in`, `room_busy`, `speaker_busy`...).", ""]
for a in agents:
    if not a["tools"]:
        continue
    out += [f"## {a['title']}", "", f"_{a['goal']}_", ""]
    for t in a["tools"]:
        props = t["parameters"].get("properties", {})
        req = set(t["parameters"].get("required", []))
        out += [f"### `{t['name']}` · {t['level']} ({LEVEL[t['level']]})", "", t["description"], "",
                f"- **Efeito:** {t['effect']}", f"- **Papéis autorizados:** {', '.join(t['roles'])}", ""]
        if props:
            out += ["| Parâmetro | Tipo | Obrigatório | Descrição |", "|---|---|---|---|"]
            for k, v in props.items():
                typ = v.get("type", "object") + (f" ({'/'.join(v['enum'])})" if v.get("enum") else "") + (" · nullable" if v.get("nullable") else "")
                if v.get("type") == "array" and "items" in v:
                    typ = f"array<{v['items'].get('type', 'object')}>"
                out.append(f"| `{k}` | {typ} | {'sim' if k in req else 'não'} | {v.get('description', '')} |")
            out.append("")
        else:
            out += ["Sem parâmetros: o escopo (usuário e evento) vem do token e da execução, nunca do modelo.", ""]
out += ["## Ferramenta de encerramento: `final_answer`", "",
        "Cada agente termina chamando `final_answer`, com schema próprio (`ParticipantFinal`, `OpsFinal`). O modo `ANY` do function calling obriga o modelo a sempre chamar uma tool, e a resposta final passa pelo **guardrail de saída** (grounding das evidências, propostas criadas, investigação prévia) antes de ser aceita.", "",
        "## O que NÃO é ferramenta", "", "Aprovar ou rejeitar propostas, executar planos, notificar inscritos e ler dados pessoais. São rotas e código determinístico acionados por humanos (`/proposals/{id}/approve|reject`)."]
Path("docs/contratos-tools.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("ok", sum(len(a["tools"]) for a in agents), "tools")
