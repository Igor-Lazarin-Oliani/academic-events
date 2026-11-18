# prompt.md: contexto do projeto (não perder o fio)

> Arquivo de memória do projeto. Leia este arquivo **antes** de continuar o trabalho em uma nova sessão (humana ou de IA).
> Atualize a seção "Decisões tomadas" e o "Log de sessões" sempre que algo for decidido.

## 1. Pedido original (resumo fiel)

Trabalho para a disciplina **Técnicas Avançadas em Desenvolvimento de Software** (TADS · UFMS, Prof. Vitor Mesaque Alves de Lima): fazer **um sistema com software agêntico**.

O que foi pedido:
1. Analisar os dois PDFs da disciplina (`Aula_Software_com_Agentes_de_IA_TADS (1).pdf` e `Contexto_Governado_Grafos_e_Agentes_OpenWebUI.pdf`) e definir a melhor forma de fazer o trabalho, com ideias e planejamento, em um `.md`.
2. Usar como base uma ideia já implementada em outro projeto: `C:\Users\igorl\Desktop\Comp\Projetos\Trabalho-CD-2026-2\events-tickets-ms` (plataforma de eventos, ingressos e registro de atividades, feita em microsserviços para a disciplina de Computação Distribuída).
3. **Inserir software agêntico** nessa ideia, com as mudanças necessárias para um **trabalho nota 10**.
4. Seguir a **arquitetura de diretórios** do projeto anterior como inspiração.
5. **Não precisa** ser microsserviços nem ter todos aqueles contêineres: deve ser uma **aplicação funcional que resolva um problema real**.
6. Se a ideia não for boa o bastante para "resolver um problema", propor outra.
7. Fazer um **frontend digno de sistema final**, não uma tela de teste como a do projeto anterior.
8. **Perguntar** o que for necessário para montar o core do projeto.
9. Manter os documentos de apoio na pasta `docs/`.

## 2. Material da disciplina (resumo do que é avaliado)

**Critérios do projeto final:** problema e justificativa agêntica (15%), arquitetura e responsabilidades (25%), contexto, tools e segurança (15%), qualidade da solução (20%), testes, evals e observabilidade (15%), demonstração e documentação (10%).

**Entregáveis:** repositório, README arquitetural, diagrama, testes/evals e demonstração final.

**Checklist do laboratório (Contexto Governado):** ferramentas (30%), contexto com fonte identificável (25%), governança (escopo, validação, aprovação) (20%), confiabilidade (não alucinar, erro tratado) (15%), clareza (10%).

**Conceitos-chave:** loop agêntico com critério de parada; orchestrator como código convencional; tools como contratos tipados; contexto ≠ estado ≠ memória ≠ conhecimento; RAG e grafo com proveniência; padrões multiagente (handoff, manager, paralelo, evaluator-optimizer); grafo de estados com checkpoint e human-in-the-loop; ports & adapters; níveis de autonomia L0 a L3; timeout, retry, budget, idempotência, circuit breaker; trace da trajetória; evals (inclusive recusas corretas: "não sei" e "não posso"); "o LLM solicita, o sistema autoriza e registra".

## 3. Proposta escolhida (confirmada em 17/11/2026)

**Plataforma de gestão de eventos acadêmicos com agentes de IA**, reescrita como monólito modular (FastAPI + PostgreSQL/pgvector + React).

Agentes:
- **Roteador (triage):** classifica e faz o handoff.
- **Assistente do Participante:** RAG do regulamento, os próprios ingressos, ações L2 com confirmação.
- **Agente de Operações:** ocorrência → grafo de impacto → alternativas → plano `PENDING`.
- **Agente Revisor:** evaluator-optimizer sobre comunicados e planos.

Detalhes completos em [`planejamento.md`](planejamento.md).

## 4. Decisões tomadas

| # | Decisão | Valor | Data |
|---|---|---|---|
| — | Formato | Aplicação única (sem microsserviços), frontend de produto | 17/11/2026 |
| — | Docs de apoio | Pasta `docs/` (`planejamento.md`, `prompt.md`) | 17/11/2026 |
| Q1 | Ideia | Eventos acadêmicos com 3 agentes (Participante, Operações, Revisor) | 17/11/2026 |
| Q2 | Provedor de LLM | **Gemini (free tier)** via `google-genai`; `FakeModel` nos testes | 17/11/2026 |
| Q3 | Backend | Python 3.12 + FastAPI + SQLAlchemy 2 + PostgreSQL 16 (em Docker; o Python local é 3.9) | 17/11/2026 |
| Q4 | Orquestração | Orquestrador próprio (grafo de estados) com ports & adapters | 17/11/2026 |
| Q5 | Grupo e prazo | **Individual, 4 dias** → MVP cortado (seção 0 do planejamento) | 17/11/2026 |
| Q8 | Frontend | React + Vite + TS + Tailwind + shadcn/ui | 17/11/2026 |
| Q9 | Nome do sistema | **academic-events** | 17/11/2026 |
| — | Repositório | Desenvolvimento local nesta pasta; o usuário cria o repositório git depois | 17/11/2026 |
| — | Modelos Gemini | `gemini-3.5-flash` (principal), `gemini-3.5-flash-lite` (leve e fallback), `gemini-3.1-flash-lite` (fallback); ver D5 | 17/11/2026 |

## 5. Regras para quem continuar o trabalho

- Responder e documentar **em português**.
- Não transformar o sistema em "chat com prompt gigante": cada agente precisa de objetivo, tools, decisão delegada e critério de parada claros.
- Toda ação com efeito passa por **proposta + aprovação** fora do agente; a autorização fica no **backend**, nunca só no prompt.
- O sistema precisa funcionar **sem o LLM** (modo degradado).
- Manter `docs/decisoes.md` no formato D1, D2… do projeto anterior.
- Testes de orquestração usam `FakeModel` (sem custo); evals usam o modelo real.

## 6. Log de sessões

- **17/11/2026:** análise dos PDFs e do `events-tickets-ms`; criação do `planejamento.md` e deste `prompt.md`; perguntas Q1 a Q5 respondidas (eventos acadêmicos, Gemini free tier, FastAPI + orquestrador próprio, individual em 4 dias); planejamento atualizado para v0.2 com corte de escopo e cronograma de 4 dias. **Próximo passo: Dia 1 (fundação + núcleo agêntico).**
- **17/11/2026 (Dia 1, concluído):** backend FastAPI + PostgreSQL em Docker; domínio (auth JWT com papéis, eventos/sessões/salas/palestrantes, inscrições com reserva atômica, conflito, limite de minicursos, troca atômica, check-in, aprovações com dry-run e execução tudo ou nada, notificações, chamados, auditoria); conhecimento (ingestão Markdown, full-text com proveniência e versão, grafo de impacto); núcleo agêntico (ModelPort, GeminiAdapter com fallback e circuit breaker, FakeModel, AgentLoop com `final_answer` e guardrail de grounding, StateGraph com checkpoint, Tool Gateway, guardrail de injeção, RunRecorder/trace); seed "Semana Acadêmica FACOM 2026" (166 usuários, 17 sessões, 886 ingressos, regulamento, FAQ e mural "envenenado") + Hackathon; **46 testes pytest passando**; `docs/decisoes.md` (D1–D13). **Próximo: Dia 2, os agentes (tools reais, prompts, Assistente do Participante, Operações + Revisor, endpoints SSE, evals).**

- **17/11/2026 (Dia 2, concluído):** tools reais (participante: 7; operações: 6), prompts versionados (`backend/app/agentic/prompts/*.md`), Context Builder (contrato JSON), Assistente do Participante (tier light, memória de curto prazo, tools terminais e guarda de chamada duplicada no loop), Agente de Operações como grafo de estados (INVESTIGATE→VALIDATE→REVIEW→PROPOSE→HUMAN_APPROVAL, até 2 revisões), Revisor (checagens determinísticas + LLM com schema), ligação aprovação→run (fecha DONE/CANCELLED), API `/assistant/chat` e `/operations/incidents` com SSE, `/runs`, `/runs/stats`, `/agents`, `/evals/latest`; 55 testes pytest; suíte de evals (`evals/run.py`, 22 casos); docs `agentes.md` e `evals.md`. Demo real validada: ocorrência "Helena não pode quinta, pode sexta de manhã" → plano S12 para sexta 10h00 sem conflitos → Revisor aprovou → organizadora aprovou → 84 notificações. **Observação:** `gemini-3.5-flash` está instável (503/timeout); o fallback para Flash-Lite cobre. **Próximo: Dia 3, o frontend.**

- **18/11/2026 (Dia 3, concluído):** frontend React 18 + Vite + TS + Tailwind (componentes próprios no estilo shadcn, tema claro/escuro, responsivo), TanStack Query, recharts, qrcode.react. **Portal:** catálogo, página do evento (programação por dia/tipo, inscrição com confirmação, palestrantes, regulamento/FAQ renderizado), login com contas demo, cadastro, Meus ingressos (QR Code, cancelamento, confirmações L2 pendentes, chamados), sino de notificações, **assistente flutuante** com trajetória ao vivo (SSE), fontes clicáveis e cartões de confirmação. **Painel:** visão geral (KPIs, gráfico, agentes), Ocorrências (grafo de estados e trajetória ao vivo, plano proposto), Central de Aprovações (antes/depois, destinatários, comunicado, parecer do Revisor, aprovar/rejeitar), Inscritos (filtro, CSV), Check-in (código ou câmera via BarcodeDetector), Chamados, Grafo do evento (SVG interativo + impacto), Base de conhecimento (versões, teste de recuperação, publicação), Trajetórias (lista, métricas, detalhe com contrato de contexto e checkpoint), Evals, Arquitetura (`/agents`), Auditoria. Docker: `frontend` (nginx) em **http://localhost:8080** com `/api` sem buffer para SSE. **E2E Playwright** (`e2e/`) passando: chat→troca→confirmação e ocorrência→plano→aprovação→execução, com o modelo real. Backend: rota `GET /events/{id}/knowledge/{doc_id}`. **Próximo: Dia 4 (README arquitetural, diagramas, vídeo, ensaio da demo, ajustes finais).**

- **18/11/2026 (Dia 4):** `README.md` arquitetural (problema, agentes, arquitetura, mapa dos critérios de avaliação e do checklist do laboratório, testes e evals, estrutura, limitações), `docs/arquitetura.md` (contêineres, módulos e ports, sequência do assistente, grafo de estados, contexto/memória, governança, observabilidade), `docs/contratos-tools.md` gerado do código por `scripts/gen_tool_contracts.py`, `docs/roteiro-demo.md` (roteiro de 8 a 10 min por critério + perguntas da defesa), screenshots em `docs/img/`, rodada final dos evals: 6 execuções no total, final **21/22** (P08 instável, seguro, documentado como limitação); correções vindas dos evals: degradação controlada de tools indisponíveis e quarentena de seções envenenadas (D19); 58 testes pytest; E2E 17 telas + 2 fluxos OK no Docker. **Pendente com o usuário:** gravar o vídeo, criar o repositório git e gerar uma nova chave do Gemini.

### Como rodar (estado atual)
- `docker compose up -d --build` → **aplicação em http://localhost:8080**; API em http://localhost:8000 (Swagger em `/docs`)
- Frontend em modo dev (hot reload): `cd frontend && npm install && npm run dev` → http://localhost:5173 (proxy `/api` → :8000)
- E2E pela UI: `cd e2e && npm install && npm run setup && npm run screens && npm run flows` (banco recém-semeado; os fluxos alteram dados, então rode `docker compose down -v && docker compose up -d` depois)
- Testes: `docker compose exec backend pytest`
- Logins (senha `senha123`): `participante@exemplo.com` (Lucas), `maria@exemplo.com`, `ana.org@exemplo.com` (organizadora da Semana), `bruno.org@exemplo.com` (organizador do Hackathon), `carla.staff@exemplo.com` (credenciamento), `admin@exemplo.com`
- Reset do banco: `docker compose down -v && docker compose up -d`
- Evals (modelo real, banco próprio `academic_events_eval`): `docker compose exec backend python /evals/run.py` (opções: `--only P01,O01`, `--category injecao`, `--delay 3`)
- Testar a API no Git Bash: use `export MSYS_NO_PATHCONV=1` e um cliente Python (o curl do Git Bash envia os acentos em Latin-1)
