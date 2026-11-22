# Decisões do projeto

Decisões do `academic-events` e suas justificativas, numeradas em ordem cronológica (mesmo formato do `events-tickets-ms`). As que deixarem de valer continuam registradas e são marcadas como substituídas.

## D1: Monólito modular em vez de microsserviços

**Status:** Em vigor.

O foco da disciplina é a arquitetura **agêntica**, não a distribuída. Um processo (FastAPI) e um banco (PostgreSQL) reduzem a complexidade operacional e deixam a demo confiável. As fronteiras continuam explícitas por módulos (`modules/*` para o domínio determinístico, `knowledge` para o contexto, `agentic` para agentes, ports e adapters) e por contratos (schemas Pydantic). Gateway NGINX, RabbitMQ, outbox e três bancos do projeto anterior foram descartados.

## D2: Regras de inscrição herdadas do events-tickets-ms

**Status:** Em vigor.

Continuam valendo: reserva atômica por `UPDATE` condicional, idempotência pelo `id` do ingresso, cancelamento como soft delete que devolve a vaga uma única vez, alteração de capacidade que preserva as vagas ocupadas, índice único parcial (uma inscrição ativa por pessoa e por sessão) e check-in só a partir de `CONFIRMED`. Como agora é um processo só, reserva e ingresso ficam na mesma transação, e a compensação deixou de ser necessária.

## D3: As vagas ficam na sessão, não no evento

**Status:** Em vigor.

Eventos acadêmicos têm programação: palestras, minicursos e workshops com salas e capacidades diferentes. A inscrição é por sessão. Isso cria as regras de conflito de horário e de limite de minicursos e, principalmente, o **grafo** evento → sessão → sala/palestrante, que o Agente de Operações usa para analisar impacto.

## D4: Orquestrador próprio, sem framework de agentes

**Status:** Em vigor.

`AgentLoop` (loop agêntico) e `StateGraph` (grafo de estados com checkpoint) somam cerca de 250 linhas e ficam atrás de ports (`ModelPort`, `ToolGateway`, `RunRecorder`). É mais fácil de defender, de testar com `FakeModel` e de trocar de provedor ("frameworks são implementação, não arquitetura").

## D5: Gemini via REST, com cadeia de fallback

**Status:** Em vigor.

O adapter chama `generateContent` diretamente com `httpx`, sem SDK: há controle total de timeout, retry e fallback, e as partes originais da resposta (com `thoughtSignature`) voltam intactas no histórico. Nos testes de 17/11/2026, o `gemini-3.5-flash` respondeu 503 (alta demanda) e o `gemini-flash-latest` passou de 90 s, enquanto os modelos Flash-Lite responderam em cerca de 1 s. Por isso: timeout de 25 s, retry só em 429/5xx (nunca em timeout) e fallback para `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite`, com circuit breaker por modelo.

## D6: Resposta final como tool (`final_answer`) e modo ANY

**Status:** Em vigor.

O modelo é obrigado a chamar uma tool a cada turno (`functionCallingConfig.mode = ANY`), e a resposta final é a tool `final_answer`, com schema Pydantic. Isso dá saída estruturada, um critério de parada explícito e um ponto único para o **guardrail de saída**: a resposta só pode citar evidências que alguma tool devolveu nesta execução, e `kind=answer` exige evidência (senão o agente deve usar `abstain`).

## D7: Autorização no Tool Gateway, nunca no prompt

**Status:** Em vigor.

O usuário da tool vem do token, nunca dos argumentos do modelo. O gateway aplica, nesta ordem: allowlist do agente → papel do usuário → validação dos argumentos → execução num SAVEPOINT com `statement_timeout` → resultado estruturado (`{ok, data|error}`) → trace. Um acesso negado (403) vira um passo `guardrail/access_denied` na trajetória.

## D8: Aprovação humana fora do alcance do agente

**Status:** Em vigor.

As tools só criam `ActionProposal` (`PENDING`). As rotas `/proposals/{id}/approve|reject` não são tools. Uma ação L2 (cancelar ou trocar o próprio ingresso) só pode ser confirmada pelo próprio participante; uma L3 (plano de ação), só por um organizador **daquele** evento. A execução é determinística e tudo ou nada (SAVEPOINT), e decidir duas vezes responde `409` sem executar de novo.

## D9: Plano validado em dry-run antes de chegar ao humano

**Status:** Em vigor.

Ao propor um plano, o backend aplica os passos dentro de um SAVEPOINT e desfaz tudo (`dry_run_plan`). Assim, o organizador só vê planos viáveis (sala livre, capacidade suficiente, palestrante sem conflito), e o impacto exibido é calculado pelo backend, não pelo modelo.

## D10: Busca lexical com proveniência; vetorial fica para depois

**Status:** Em vigor.

Full-text do PostgreSQL (`portuguese`) sobre um texto normalizado sem acentos, com escopo por `event_id` e somente documentos `ACTIVE` aplicados **no SQL**. Cada trecho carrega `source_id`, seção, versão, data e confiabilidade (`OFFICIAL`/`UNVERIFIED`). Uma nova versão torna a anterior `SUPERSEDED`. A busca vetorial (pgvector) é um próximo passo e não muda o contrato da tool.

## D11: Dados pessoais fora do LLM e do trace

**Status:** Em vigor.

O seed é 100% fictício (o Gemini free tier pode usar os dados para treinamento). As tools de operações devolvem contagens, não listas de e-mails. Os destinatários das notificações são resolvidos pelo código na execução. O trace mascara e-mails.

## D12: Sem migrações; tabelas por `create_all`

**Status:** Em vigor (como a D8 do projeto anterior).

Adequado a um trabalho sem dados a preservar. Para mudar o modelo, rode `docker compose down -v`. O seed roda no startup quando o banco está vazio.

## D13: Testes contra PostgreSQL real

**Status:** Em vigor.

As regras dependem do PostgreSQL (UPDATE condicional, índice parcial, full-text, `statement_timeout`, SAVEPOINT). Os testes usam o banco `academic_events_test` no mesmo contêiner, e os testes de agente usam `FakeModel`, sem rede nem custo.

## D14: Tools terminais e guarda de chamada duplicada no loop

**Status:** Em vigor.

No primeiro teste real, o Flash-Lite criou a proposta de troca e depois passou 5 turnos "explorando" a programação até estourar o budget. Em vez de depender só do prompt, o **orquestrador** passou a controlar o fluxo: depois de uma tool terminal bem-sucedida (`propose_*`, `escalate_to_organizer`), o modelo só enxerga `final_answer`. A mesma tool com os mesmos argumentos não é executada duas vezes (`guardrail/duplicate_call`). Resultado: a mesma tarefa caiu de 26 para 3 passos.

## D15: Modelo por agente (tier) e cadeia de fallback longa

**Status:** Em vigor. Atualiza a D5.

O Assistente e o Revisor usam o tier `light` (Flash-Lite: ~1 s por chamada, suficiente para essas tarefas); o Agente de Operações usa o `default` (Flash). No free tier, a cota é **por modelo**, então uma cadeia longa aumenta a capacidade total: `light → 3.1-flash-lite → flash-lite-latest → flash`. O HTTP 429 (cota) vai direto ao próximo modelo, sem retry, porque a cota não volta em segundos. O Gemma foi testado e descartado (passou de 30 s com `systemInstruction`).

## D16: O sistema, não o modelo, acrescenta a notificação ao plano

**Status:** Em vigor.

O Agente de Operações não tem um passo de notificação: o grafo acrescenta `NOTIFY_PARTICIPANTS` para as sessões tocadas pelo plano, e os destinatários são resolvidos pelo código na execução. Isso evita que o modelo escolha quem notificar e mantém os dados pessoais fora do contexto. Os evals conferem os destinatários contra um oráculo SQL.

## D17: Revisor híbrido (determinístico + LLM)

**Status:** Em vigor.

As checagens objetivas (horários, datas, salas e sessões citados batem com os fatos do dry-run; os novos valores aparecem) são código, porque um LLM pode aprovar um comunicado com horário errado, e isso não pode depender do modelo. O teste do grafo simula exatamente esse caso: o LLM do Revisor aprova, a checagem determinística reprova e o agente corrige. O LLM avalia o que é semântico (clareza, completude, promessas indevidas) com saída JSON por schema. Se o LLM cair, valem só as checagens determinísticas, e isso fica registrado.

## D18: Frontend como produto, com a trajetória do agente visível

**Status:** Em vigor.

React + Vite + TypeScript + Tailwind, com componentes próprios no estilo shadcn/ui, sem CLI geradora e sem dependências de UI pesadas. O chat e a tela de ocorrências consomem SSE (`fetch` + `ReadableStream`, porque `EventSource` não faz POST) e mostram cada passo do agente em linguagem humana: "Analisando o impacto no grafo… 84 inscritos afetados". A explicabilidade fica para o usuário final, não só para o desenvolvedor. As ações L2 aparecem como **cartões de confirmação** fora do texto do chat, e a aprovação L3 tem uma tela própria com antes/depois e o parecer do Revisor. Em produção, o nginx serve o build e encaminha `/api` com `proxy_buffering off`. O token JWT fica no `localStorage` por simplicidade: é um trade-off conhecido (risco de XSS) e aceitável para o trabalho. Em produção, o caminho seria um cookie `HttpOnly`.

## D19: Degradação controlada de tools e quarentena de trechos envenenados

**Status:** Em vigor. Origem: evals das execuções 3 e 4.

- **Tool fora do ar:** uma tool que respondeu 503 fica marcada como indisponível pelo resto da execução e não é chamada de novo (`guardrail/tool_unavailable_skip`). Depois de 2 turnos seguidos só com indisponibilidade, o orquestrador deixa o modelo ver apenas `final_answer` (e `escalate_to_organizer`), para que ele diga honestamente "indisponível agora" em vez de gastar o budget (`guardrail/tools_unavailable`).
- **Injeção em documento:** a primeira versão removia só as **frases** com instrução; uma frase vizinha com desinformação ("o certificado vale 40 horas") passou. Agora a **seção recuperada inteira** vai para quarentena quando contém instrução embutida. O conteúdo de um trecho comprometido não é confiável como um todo.
