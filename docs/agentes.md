# Ficha dos agentes

Responde ao checklist da aula ("antes de chamar algo de agente"): objetivo, decisão delegada, tools permitidas e proibidas, estado, quem controla o loop, condição de término, aprovação humana, como testar e como observar. A versão "viva" desta ficha está em `GET /agents` (tela **Arquitetura** do painel).

## Resumo em linguagem simples

O sistema tem **3 agentes**, usados só onde há linguagem livre ou investigação. O que é regra fixa (vagas, inscrição, check-in, execução de mudanças) é código determinístico.

**1. Assistente do Participante** (chat "Pergunte ao assistente", no portal). Substitui a fila de dúvidas no WhatsApp.
- Responde com base no regulamento, no FAQ, na programação e nos ingressos **do próprio usuário**, e **cita a fonte** (ex.: "Regulamento §4.2").
- Diz **"não sei"** quando a informação não existe e oferece encaminhar à comissão.
- Diz **"não posso"** para ingressos de outras pessoas, mudanças na programação e instruções maliciosas.
- **Prepara** cancelamentos e trocas de sessão como um **cartão de confirmação**; nada acontece até o participante clicar em "Confirmar".
- **Abre chamado** para a comissão quando o pedido exige decisão humana (ex.: intérprete de Libras).

**2. Agente de Operações** (tela "Ocorrências", no painel da comissão). Ajuda a resolver imprevistos.
- Recebe a ocorrência em texto livre ("a palestrante não pode quinta à tarde, pode sexta de manhã").
- **Investiga o impacto** no grafo do evento: sessões e inscritos afetados.
- **Busca alternativas reais**: horários com palestrante e sala livres e o menor número de inscritos com conflito.
- Monta o **plano** e **escreve o comunicado**. **Não executa nada**: o sistema simula o plano, o Revisor confere e o plano vai para a **Central de Aprovações**; só a aprovação de um organizador aplica as mudanças e notifica os inscritos.

**3. Agente Revisor** (dentro do fluxo de Operações). Confere o comunicado antes de ele chegar ao organizador.
- **Em código:** todas as datas, horários, salas e sessões citados precisam bater com o plano validado (ex.: o texto diz "10h00", mas o novo horário é "08h00" → reprova).
- **Pelo modelo:** clareza, completude e promessas além dos fatos.
- Se reprovar, devolve o comunicado ao Agente de Operações com os problemas apontados, e o agente o corrige no máximo 2 vezes.

**O que nenhum agente pode fazer:** aprovar, executar mudanças, notificar inscritos ou ver nomes e e-mails de participantes. Os agentes **propõem**; pessoas e código **decidem e executam**. Cada execução fica registrada passo a passo na tela **Trajetórias**.

## Roteamento (determinístico, sem LLM)

| Quem | Para onde | Por quê |
|---|---|---|
| Qualquer usuário autenticado no chat do portal | Assistente do Participante | o escopo é o próprio usuário |
| Organizador/admin **do evento** em "Ocorrências" | Agente de Operações | `ensure_can_manage_event` antes de qualquer chamada ao modelo |
| Agente de Operações → Revisor | Revisor (handoff dentro do grafo) | evaluator-optimizer |

Um participante nunca chega ao Agente de Operações: isso não é decidido pelo modelo.

## 1. Assistente do Participante

| Item | Definição |
|---|---|
| Objetivo | Resolver dúvidas e solicitações do participante sobre o evento, a programação, o regulamento e **os próprios ingressos** |
| Decisão delegada ao modelo | quais fontes consultar; se responde, se abstém, se recusa, se propõe uma ação ou se escala |
| Padrão | agente único + tools (slide 27 da aula de contexto governado) |
| Modelo | tier `light` (`gemini-3.5-flash-lite`), com fallback |
| Tools | `search_event_knowledge` (L0), `get_event_schedule` (L0), `list_my_tickets` (L0), `get_ticket_status` (L0, 403 para ingresso alheio), `propose_ticket_cancellation` (L2), `propose_session_swap` (L2, já validada em dry-run), `escalate_to_organizer` (L1) |
| Não pode | ver dados de outros participantes, alterar a programação, executar cancelamento/troca, aprovar qualquer coisa |
| Estado | `agent_runs` + `agent_steps` (trajetória); memória de curto prazo = últimas 6 mensagens da conversa (`conversation_messages`) |
| Contexto | contrato JSON (escopo, dias do evento, fontes disponíveis, políticas, budget); conhecimento e dados **sob demanda** pelas tools |
| Quem controla o loop | `AgentLoop` (código): modo ANY, allowlist, guarda de chamada duplicada, **tools terminais** (depois de propor ou escalar, só resta `final_answer`), **degradação controlada** (tool com 503 não é chamada de novo na execução; após 2 turnos só com indisponibilidade, só restam `final_answer`/`escalate_to_organizer`; D19) |
| Conteúdo recuperado | seção com instrução embutida vai **inteira para quarentena** (não só a frase); documentos `UNVERIFIED` não viram regra (D19) |
| Término | `final_answer` válida (schema + grounding: só cita evidências devolvidas pelas tools; `answer` exige evidência), `max_steps=8`, `max_tokens`, timeout de 120 s, modelo indisponível (modo degradado) |
| Aprovação humana | L2: o **próprio participante** confirma no cartão da UI (`POST /proposals/{id}/approve`, que não é tool) |
| Testes | `test_agents.py` (FakeModel) + evals `P01`–`P15` |
| Observação | trajetória ao vivo (SSE) e tela "Trajetórias"; guardrails `access_denied`, `injection_redacted`, `input_injection`, `output_grounding`, `duplicate_call`, `terminal_tool`, `tool_unavailable_skip`, `tools_unavailable`, `budget_exceeded` |

## 2. Agente de Operações

| Item | Definição |
|---|---|
| Objetivo | Transformar uma ocorrência em linguagem natural num **plano de ação verificável** para aprovação da comissão |
| Decisão delegada | identificar o elemento afetado e a janela; escolher entre as alternativas reais; montar os passos; redigir o comunicado |
| Padrão | **grafo de estados** + evaluator-optimizer + human-in-the-loop |
| Modelo | tier `default` (`gemini-3.5-flash`), com fallback para Flash-Lite |
| Tools (todas L0) | `get_event_overview`, `query_impact_graph` (grafo), `find_alternative_slots`, `find_available_rooms`, `search_event_knowledge`, `validate_plan` (dry-run) |
| Não pode | executar o plano, notificar diretamente, ver nomes ou e-mails de inscritos (só contagens) |
| Grafo | `INVESTIGATE → VALIDATE → REVIEW → PROPOSE → HUMAN_APPROVAL ⏸`; revisões voltam a `INVESTIGATE` (no máximo 2); `need_info`/`no_action`/`refusal` → `DONE`; checkpoint em `agent_runs.state` a cada transição |
| Guardrail de saída | `kind=plan` exige passos, comunicado e **investigação prévia** (`query_impact_graph`) |
| O que o sistema faz (não o modelo) | acrescenta o passo `NOTIFY_PARTICIPANTS` às sessões tocadas, valida em dry-run, calcula impacto e destinatários |
| Término | proposta criada (pausa em `HUMAN_APPROVAL`), `need_info`/`no_action`/`refusal`, revisões esgotadas, budget (`max_steps=14`), modelo indisponível |
| Aprovação humana | L3: organizador **daquele** evento na Central de Aprovações; a execução é determinística, tudo ou nada e idempotente, e a run fecha como `DONE`/`CANCELLED` |
| Testes | `test_agents.py` (grafo completo com revisão) + evals `O01`–`O05` (com oráculo SQL dos destinatários) |

## 3. Agente Revisor

| Item | Definição |
|---|---|
| Objetivo | Garantir que o comunicado é fiel aos fatos validados, completo, claro e sem dados pessoais |
| Decisão delegada | aprovar ou devolver com problemas objetivos e sugestões |
| Padrão | evaluator (checagens determinísticas + LLM como função, com saída JSON por schema) |
| Modelo | tier `light`; se indisponível, valem só as checagens determinísticas (registrado como `llm_skipped`) |
| Checagens determinísticas | todos os horários, datas, salas e sessões citados existem nos fatos do dry-run; o novo horário e a nova sala são citados; tamanho de título e corpo |
| Tools | nenhuma |
| Término | uma chamada (parecer) |
| Testes | `test_agents.py` (reprova horário errado) + evals `R01`/`R02` |
