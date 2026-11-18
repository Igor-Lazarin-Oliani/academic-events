# Arquitetura

Visão detalhada da arquitetura do `academic-events`. O resumo e o mapa dos requisitos estão no [README](../README.md); as justificativas, em [decisoes.md](decisoes.md).

## 1. Visão de contêineres

```mermaid
flowchart LR
    U["Navegador<br/>participante · comissão · credenciamento"]
    subgraph compose["docker compose"]
        FE["frontend<br/>nginx + React (build)<br/>:8080"]
        BE["backend<br/>FastAPI (monólito modular)<br/>:8000"]
        DB[("db<br/>PostgreSQL 16")]
    end
    LLM["Gemini API<br/>(cadeia de modelos)"]
    U -->|HTTPS| FE
    FE -->|"/api → REST + SSE<br/>(proxy_buffering off)"| BE
    BE --> DB
    BE -->|"ModelPort / GeminiAdapter<br/>timeout · retry · fallback · circuit breaker"| LLM
```

Três contêineres. Não há microsserviços (D1): as fronteiras são módulos e contratos.

## 2. Módulos do backend (ports & adapters)

```mermaid
flowchart TB
    subgraph api["Camada HTTP (routers)"]
        R1["auth · events · tickets · approvals<br/>notifications · activity · knowledge"]
        R2["agentic/api<br/>/assistant/chat · /operations/incidents (SSE)<br/>/runs · /runs/stats · /agents · /evals/latest"]
    end
    subgraph core["Núcleo agêntico (app/agentic)"]
        AG["agents/<br/>participant · operations · reviewer"]
        OR["orchestrator/<br/>AgentLoop · StateGraph · Budget · CircuitBreaker"]
        TG["tools/<br/>Tool Registry · Tool Gateway"]
        GR["guardrails/<br/>injection · output grounding"]
        CB["context/<br/>Context Builder (contrato JSON)"]
        PT["ports/ModelPort"]
        AD["adapters/<br/>GeminiAdapter · FakeModel"]
        TR["tracing/RunRecorder<br/>(StatePort + TracePort)"]
    end
    subgraph dom["Domínio determinístico (app/modules)"]
        D1["events/sessions · tickets<br/>(reserva atômica, conflito, limite, troca)"]
        D2["approvals<br/>(dry-run, execução tudo-ou-nada)"]
        D3["notifications · activity (auditoria)"]
    end
    KN["knowledge/<br/>ingestão · busca full-text · grafo de impacto"]
    R2 --> AG
    R1 --> dom
    AG --> OR
    OR --> PT
    PT -.implementa.-> AD
    OR --> TG
    TG --> GR
    TG --> dom
    TG --> KN
    AG --> CB
    OR --> TR
    D2 --> D1
```

| Port | Contrato | Adapters |
|---|---|---|
| `ModelPort` | `generate(system, messages, tools, force_tool, response_schema, tier)` → `ModelResponse` (texto, tool_calls, uso, tentativas) | `GeminiAdapter` (REST), `FakeModel` (testes) |
| `ToolGateway` | `execute(name, args, ctx, allowed)` → `{ok, data \| error}` | tools Python locais (`participant_tools`, `ops_tools`) |
| `RunRecorder` | `step()`, `checkpoint()`, `pause()`, `finish()` | PostgreSQL (`agent_runs`, `agent_steps`) com sessão própria e commit por passo |

Trocar o provedor de LLM é só escrever um novo adapter: nenhum agente, tool ou regra de domínio muda.

## 3. Assistente do Participante: loop agêntico

```mermaid
sequenceDiagram
    autonumber
    actor P as Participante
    participant UI as Chat (SSE)
    participant L as AgentLoop (orquestrador)
    participant M as Gemini (ModelPort)
    participant G as Tool Gateway
    participant D as Domínio / Conhecimento
    P->>UI: "Quero trocar o minicurso de React pelo de LLMs"
    UI->>L: POST /assistant/chat?stream=true
    L->>M: contrato de contexto + tools (modo ANY)
    M-->>L: list_my_tickets()
    L->>G: execute (allowlist, papel, schema)
    G->>D: ingressos DO USUÁRIO DO TOKEN
    D-->>G: tickets
    G-->>L: {ok, data} + evidência
    L->>M: resultado
    M-->>L: propose_session_swap(EVT-…, S08)
    L->>G: execute
    G->>D: dry-run da troca (vaga, conflito, limite) → rollback
    G->>D: cria ActionProposal PENDING (L2)
    Note over L: tool terminal → o modelo passa a ver só final_answer
    M-->>L: final_answer(kind=action_proposed, proposal_ids)
    L->>L: guardrail de saída (grounding)
    L-->>UI: passos ao vivo + resultado
    P->>UI: clica "Confirmar" no cartão
    UI->>D: POST /proposals/{id}/approve (não é tool)
    D->>D: troca atômica (cancelar + emitir) + auditoria
```

## 4. Agente de Operações: grafo de estados

```mermaid
stateDiagram-v2
    [*] --> INVESTIGATE
    INVESTIGATE --> VALIDATE: kind = plan
    INVESTIGATE --> DONE: need_info / no_action / refusal
    INVESTIGATE --> DEGRADED: modelo indisponível
    INVESTIGATE --> BUDGET_EXCEEDED: passos/tokens/tempo
    VALIDATE --> REVIEW: dry-run válido
    VALIDATE --> INVESTIGATE: inválido (≤ 2 revisões)
    VALIDATE --> FAILED: revisões esgotadas
    REVIEW --> PROPOSE: Revisor aprovou (ou revisões esgotadas, com pendências)
    REVIEW --> INVESTIGATE: Revisor devolveu (handoff)
    PROPOSE --> HUMAN_APPROVAL
    HUMAN_APPROVAL --> DONE: organizador aprova → execução determinística
    HUMAN_APPROVAL --> CANCELLED: organizador rejeita
```

- **INVESTIGATE:** loop agêntico com tools L0 (visão geral, grafo de impacto, horários alternativos, salas livres, regulamento, `validate_plan`). O guardrail exige `query_impact_graph` antes de qualquer plano.
- **VALIDATE:** o **sistema** acrescenta `NOTIFY_PARTICIPANTS` para as sessões tocadas (D16) e aplica o plano num SAVEPOINT desfeito em seguida (D9).
- **REVIEW:** Revisor híbrido (D17), com checagens determinísticas sobre os fatos do dry-run e LLM com saída JSON por schema.
- **PROPOSE:** cria a `ActionProposal` L3 com impacto calculado pelo backend (destinatários reais).
- **HUMAN_APPROVAL:** a run fica `WAITING_APPROVAL`, com checkpoint em `agent_runs.state`. A decisão humana (`/proposals/{id}/approve`) executa os passos tudo ou nada e fecha a run (`DONE`/`CANCELLED`), registrando o passo `approval` na trajetória.

## 5. Contexto, estado, memória e conhecimento

| Conceito | Implementação | Onde |
|---|---|---|
| Prompt | instruções versionadas por agente | `backend/app/agentic/prompts/*.md` |
| Contexto | contrato JSON por execução: escopo, dias do evento, fontes disponíveis, políticas e budget | `agentic/context/builder.py`, visível na tela de trajetória |
| Estado | run, passos, nó atual e checkpoint do grafo | `agent_runs`, `agent_steps` |
| Memória | curto prazo: últimas 6 mensagens da conversa | `conversations`, `conversation_messages` |
| Conhecimento | regulamento, FAQ e avisos versionados (`ACTIVE`/`SUPERSEDED`, `OFFICIAL`/`UNVERIFIED`), recuperados sob demanda | `knowledge_documents`, `knowledge_chunks` (full-text pt) |
| Grafo | projeção evento → sessão → sala/palestrante, com inscritos agregados | `knowledge/graph.py` |

## 6. Governança: onde cada controle mora

| Controle | Mecanismo | Não depende do prompt? |
|---|---|---|
| Participante só vê os próprios ingressos | tools sem `user_id`; `get_own_ticket` → 403 | ✅ |
| Organizador só opera o próprio evento | `ensure_can_manage_event` no roteamento e nas tools | ✅ |
| Agente não executa efeitos | tools L2/L3 só criam propostas; aprovação é rota humana | ✅ |
| Documento envenenado | redação das frases suspeitas + `trust=UNVERIFIED` | ✅ (o prompt reforça) |
| Resposta sem fonte | guardrail de grounding na `final_answer` | ✅ |
| Loop infinito / custo | budget (passos, tokens, tempo), tool terminal, chamada duplicada | ✅ |
| LGPD | o LLM vê contagens; e-mails mascarados no trace; seed fictício | ✅ |
| Escopo do conhecimento | filtro `event_id` + `ACTIVE` no SQL | ✅ |

## 7. Observabilidade

- **Trajetória por execução** (`agent_steps`): `run.start` (com o contrato de contexto), `model.call` (modelo efetivo, tentativas/fallback, tokens, latência), `tool.call`/`tool.result` (status, duração), `guardrail`, `transition`, `validation`, `review`, `handoff`, `proposal`, `approval`, `run.end`.
- **Ao vivo:** SSE no chat e na tela de ocorrências.
- **Métricas:** `GET /runs/stats` (execuções por agente e status, latência p50/p95, tokens, taxa de erro de tools, guardrails acionados), no painel.
- **Auditoria de domínio:** `activity_logs` na mesma transação da mudança, com `source` (`api`/`agent`/`system`), ator e `correlation_id`.
- **Correlação:** `X-Correlation-Id` liga a requisição HTTP, a run e a auditoria.
