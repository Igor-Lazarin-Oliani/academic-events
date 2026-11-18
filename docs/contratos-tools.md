# Contratos das ferramentas (tools)

> Gerado automaticamente de `GET /agents` por `scripts/gen_tool_contracts.py`. Não edite à mão.

Toda chamada passa pelo **Tool Gateway** (`backend/app/agentic/tools/gateway.py`): allowlist do agente → papel do usuário → validação Pydantic → execução num SAVEPOINT com `statement_timeout` → resultado estruturado → trace.

**Formato de resultado (sempre):**

```json
{"ok": true, "data": { ... }}
{"ok": false, "error": {"code": "ticket_out_of_scope", "message": "...", "status": 403}}
```

Códigos de erro previsíveis: `tool_not_allowed`, `forbidden` (papel), `invalid_arguments` (com `details` por campo), `unavailable` (503), `timeout` (504), `internal_error` e os erros de domínio (`sold_out`, `time_conflict`, `minicurso_limit`, `ticket_out_of_scope`, `event_out_of_scope`, `already_checked_in`, `room_busy`, `speaker_busy`...).

## Assistente do Participante

_Resolver dúvidas e solicitações do participante sobre o evento, o regulamento e os próprios ingressos._

### `search_event_knowledge` · L0 (leitura, automático)

Busca trechos do regulamento, FAQ e avisos do evento atual. Retorna source_id e section para citar como evidência.

- **Efeito:** nenhum (somente leitura)
- **Papéis autorizados:** admin, organizer, participant, staff

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `query` | string | sim | Pergunta ou palavras-chave em português |

### `get_event_schedule` · L0 (leitura, automático)

Lista a programação do evento (sessões, horários, salas, palestrantes, vagas e carga horária).

- **Efeito:** nenhum (somente leitura)
- **Papéis autorizados:** admin, organizer, participant, staff

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `day` | string · nullable | não | Data AAAA-MM-DD (opcional) |
| `kind` | string (PALESTRA/MINICURSO/MESA_REDONDA/WORKSHOP/ABERTURA) · nullable | não | Tipo de sessão (opcional) |
| `text` | string · nullable | não | Filtro por palavra no título, trilha ou palestrante (opcional) |

### `list_my_tickets` · L0 (leitura, automático)

Lista os ingressos do usuário autenticado neste evento.

- **Efeito:** nenhum (somente leitura)
- **Papéis autorizados:** admin, organizer, participant, staff

Sem parâmetros: o escopo (usuário e evento) vem do token e da execução, nunca do modelo.

### `get_ticket_status` · L0 (leitura, automático)

Consulta um ingresso do usuário autenticado pelo código. Ingressos de outras pessoas são negados.

- **Efeito:** nenhum (somente leitura)
- **Papéis autorizados:** admin, organizer, participant, staff

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `ticket_code` | string | sim | Código do ingresso, formato EVT-AAAA-XXXXXX |

### `propose_ticket_cancellation` · L2 (proposta; o próprio usuário confirma)

Cria uma SOLICITAÇÃO de cancelamento do ingresso do usuário; ele confirma na tela.

- **Efeito:** cria proposta pendente; nada é cancelado sem confirmação do usuário
- **Papéis autorizados:** admin, organizer, participant, staff

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `ticket_code` | string | sim | Código do ingresso a cancelar |
| `reason` | string | não | Motivo informado pelo usuário (opcional) |

### `propose_session_swap` · L2 (proposta; o próprio usuário confirma)

Cria uma SOLICITAÇÃO de troca de sessão, já validada (vaga, conflito, limite); o usuário confirma na tela.

- **Efeito:** cria proposta pendente; nada é trocado sem confirmação do usuário
- **Papéis autorizados:** admin, organizer, participant, staff

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `ticket_code` | string | sim | Código do ingresso atual |
| `to_session_code` | string | sim | Código da sessão de destino, ex.: S08 |

### `escalate_to_organizer` · L1 (reversível, automático + log)

Abre um chamado para a comissão organizadora quando a dúvida não pode ser resolvida aqui.

- **Efeito:** abre chamado (reversível)
- **Papéis autorizados:** admin, organizer, participant, staff

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `summary` | string | sim | Resumo da dúvida/pedido para a comissão, sem dados sensíveis |

## Agente de Operações

_Transformar uma ocorrência em um plano de ação verificável para aprovação da comissão._

### `search_event_knowledge` · L0 (leitura, automático)

Busca trechos do regulamento, FAQ e avisos do evento atual. Retorna source_id e section para citar como evidência.

- **Efeito:** nenhum (somente leitura)
- **Papéis autorizados:** admin, organizer, participant, staff

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `query` | string | sim | Pergunta ou palavras-chave em português |

### `get_event_overview` · L0 (leitura, automático)

Visão geral do evento: dias, salas (disponibilidade) e todas as sessões com inscritos.

- **Efeito:** nenhum (somente leitura)
- **Papéis autorizados:** admin, organizer

Sem parâmetros: o escopo (usuário e evento) vem do token e da execução, nunca do modelo.

### `query_impact_graph` · L0 (leitura, automático)

Análise de impacto no grafo do evento: sessões ligadas a uma sala, palestrante ou sessão, inscritos afetados e caminho.

- **Efeito:** nenhum (somente leitura)
- **Papéis autorizados:** admin, organizer

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `node_type` | string (room/speaker/session) | sim | Tipo do elemento afetado |
| `key` | string | sim | Nome da sala (ex.: Sala 105), nome do palestrante ou código da sessão (ex.: S12) |
| `start` | string · nullable | não | Início da janela afetada, ISO 8601 com -04:00 (opcional) |
| `end` | string · nullable | não | Fim da janela afetada, ISO 8601 com -04:00 (opcional) |

### `find_available_rooms` · L0 (leitura, automático)

Salas livres e disponíveis numa janela de horário, com capacidade mínima.

- **Efeito:** nenhum (somente leitura)
- **Papéis autorizados:** admin, organizer

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `start_at` | string | sim | Início, ISO 8601 com -04:00 |
| `end_at` | string | sim | Fim, ISO 8601 com -04:00 |
| `min_capacity` | integer | não | Capacidade mínima necessária (ex.: número de inscritos) |

### `find_alternative_slots` · L0 (leitura, automático)

Horários alternativos para uma sessão (palestrante livre + sala livre que comporta os inscritos), com conflitos dos inscritos.

- **Efeito:** nenhum (somente leitura)
- **Papéis autorizados:** admin, organizer

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `session_code` | string | sim | Código da sessão a remanejar, ex.: S12 |
| `day` | string · nullable | não | Restringe a uma data AAAA-MM-DD (opcional) |
| `exclude_current` | boolean | não | Ignora o horário atual da sessão |

### `validate_plan` · L0 (leitura, automático)

Valida um plano aplicando os passos em simulação (dry-run, nada é gravado). Use antes da resposta final.

- **Efeito:** nenhum (simulação desfeita)
- **Papéis autorizados:** admin, organizer

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `steps` | array<object> | sim | Passos do plano, em ordem |

## Ferramenta de encerramento: `final_answer`

Cada agente termina chamando `final_answer`, com schema próprio (`ParticipantFinal`, `OpsFinal`). O modo `ANY` do function calling obriga o modelo a sempre chamar uma tool, e a resposta final passa pelo **guardrail de saída** (grounding das evidências, propostas criadas, investigação prévia) antes de ser aceita.

## O que NÃO é ferramenta

Aprovar ou rejeitar propostas, executar planos, notificar inscritos e ler dados pessoais. São rotas e código determinístico acionados por humanos (`/proposals/{id}/approve|reject`).
