import { useState } from "react";
import { AlertTriangle, ArrowRightLeft, Bot, BrainCircuit, CheckCircle2, ChevronDown, CircleDot, FileCheck2, Flag, GitBranch, Play, ShieldAlert, ShieldCheck, UserCheck, Wrench, XCircle } from "lucide-react";
import type { Step } from "@/lib/types";
import { cn, fmt, plural } from "@/lib/utils";

export const TOOL_LABEL: Record<string, string> = {
  search_event_knowledge: "Buscando no regulamento e no FAQ",
  get_event_schedule: "Consultando a programação",
  list_my_tickets: "Consultando seus ingressos",
  get_ticket_status: "Consultando um ingresso",
  propose_ticket_cancellation: "Preparando a solicitação de cancelamento",
  propose_session_swap: "Validando a troca de sessão",
  escalate_to_organizer: "Abrindo chamado para a comissão",
  get_event_overview: "Lendo a visão geral do evento",
  query_impact_graph: "Analisando o impacto no grafo do evento",
  find_alternative_slots: "Buscando horários alternativos",
  find_available_rooms: "Buscando salas livres",
  validate_plan: "Simulando o plano (dry-run)",
};

const GUARDRAIL_LABEL: Record<string, string> = {
  access_denied: "Acesso negado pelo Tool Gateway (403)",
  injection_redacted: "Instrução embutida em documento foi removida",
  input_injection: "Tentativa de alterar as instruções detectada",
  output_grounding: "Resposta conferida contra as evidências",
  final_schema: "Resposta fora do formato esperado",
  duplicate_call: "Chamada repetida bloqueada",
  terminal_tool: "Ação registrada: o orquestrador encerra a tarefa",
  budget_exceeded: "Limite de passos/tempo atingido",
  tool_not_allowed: "Ferramenta fora da lista permitida",
  role_denied: "Papel do usuário sem permissão",
};

const NODE_LABEL: Record<string, string> = {
  INVESTIGATE: "Investigar", VALIDATE: "Validar", REVIEW: "Revisar", PROPOSE: "Propor", HUMAN_APPROVAL: "Aprovação humana",
  DONE: "Concluído", FAILED: "Falhou", DEGRADED: "Modo degradado", BUDGET_EXCEEDED: "Budget esgotado",
};

export interface StepView { icon: JSX.Element; title: string; detail?: string; tone: "brand" | "ok" | "warn" | "danger" | "muted"; meta?: string }

export function describe(s: Step): StepView | null {
  const out = s.output ?? {};
  switch (s.type) {
    case "run.start":
      return { icon: <Play className="h-3.5 w-3.5" />, title: s.agent === "operations" ? "Agente de Operações iniciou a investigação" : "Assistente recebeu a mensagem", tone: "muted" };
    case "model.call": {
      if (s.status !== "ok") return { icon: <AlertTriangle className="h-3.5 w-3.5" />, title: "Modelo indisponível: modo degradado", detail: out.error, tone: "danger" };
      const calls: string[] = (out.tool_calls ?? []).map((c: any) => c.name);
      const attempts = out.attempts ?? [];
      const fallback = attempts.length > 1 ? ` · fallback após ${plural(attempts.length - 1, "falha", "falhas")}` : "";
      const who = s.agent === "reviewer" ? "Revisor (LLM) avaliou o comunicado" : calls.includes("final_answer") ? "Modelo decidiu responder" : `Modelo decidiu: ${calls.map((c) => TOOL_LABEL[c] ?? c).join(" + ") || "pensar"}`;
      return { icon: <BrainCircuit className="h-3.5 w-3.5" />, title: who, tone: "brand", meta: `${s.name} · ${fmt.duration(s.duration_ms)} · ${(s.tokens_in ?? 0) + (s.tokens_out ?? 0)} tokens${fallback}` };
    }
    case "tool.call":
      return null;
    case "tool.result": {
      const ok = s.status === "ok";
      const data = out.data ?? {};
      let detail = ok ? "" : out.error?.message;
      if (ok && s.name === "query_impact_graph") detail = `${plural(data.affected_sessions?.length ?? 0, "sessão", "sessões")} · ${plural(data.affected_participants ?? 0, "inscrito afetado", "inscritos afetados")}`;
      if (ok && s.name === "find_alternative_slots") detail = `${plural(data.alternatives?.length ?? 0, "alternativa", "alternativas")}; melhor: ${data.alternatives?.[0]?.when ?? "—"} (${typeof data.alternatives?.[0]?.participants_with_conflict === "number" ? plural(data.alternatives[0].participants_with_conflict, "conflito", "conflitos") : "— conflitos"})`;
      if (ok && s.name === "search_event_knowledge") detail = (data.results ?? []).map((r: any) => `${r.source_id} §${r.section}`).join(", ") || "nenhum trecho";
      if (ok && s.name === "get_event_schedule") detail = plural(data.count ?? 0, "sessão", "sessões");
      if (ok && s.name === "validate_plan") detail = data.valid ? "plano válido" : `inválido: ${data.errors?.[0]?.message}`;
      return { icon: <Wrench className="h-3.5 w-3.5" />, title: TOOL_LABEL[s.name] ?? s.name, detail, tone: ok ? "ok" : "warn", meta: `${s.name} · ${fmt.duration(s.duration_ms)}${ok ? "" : ` · ${s.status}`}` };
    }
    case "guardrail": {
      const passed = s.status === "passed";
      return { icon: passed ? <ShieldCheck className="h-3.5 w-3.5" /> : <ShieldAlert className="h-3.5 w-3.5" />, title: GUARDRAIL_LABEL[s.name] ?? `Guardrail: ${s.name}`,
        detail: s.status === "rejected" ? (out.problems ?? []).join("; ") : undefined, tone: passed ? "ok" : s.status === "flagged" ? "warn" : "danger", meta: `guardrail · ${s.status}` };
    }
    case "transition": {
      const [a, b] = s.name.split("->");
      return { icon: <GitBranch className="h-3.5 w-3.5" />, title: `${NODE_LABEL[a] ?? a} → ${NODE_LABEL[b] ?? b}`, tone: "muted", meta: "grafo de estados" };
    }
    case "validation":
      return { icon: <FileCheck2 className="h-3.5 w-3.5" />, title: s.status === "passed" ? "Sistema validou o plano (dry-run)" : "Sistema recusou o plano", detail: s.status !== "passed" ? out.errors?.[0]?.message : undefined, tone: s.status === "passed" ? "ok" : "danger", meta: "determinístico" };
    case "review":
      if (s.name === "deterministic") return { icon: <FileCheck2 className="h-3.5 w-3.5" />, title: "Revisor: checagem determinística dos fatos", detail: (out.issues ?? []).join("; ") || "datas, horários e salas conferem", tone: out.issues?.length ? "warn" : "ok" };
      if (s.name === "verdict") return { icon: s.status === "approved" ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />, title: s.status === "approved" ? "Revisor aprovou o comunicado" : "Revisor devolveu para correção", detail: (out.issues ?? []).join("; "), tone: s.status === "approved" ? "ok" : "warn" };
      return { icon: <FileCheck2 className="h-3.5 w-3.5" />, title: "Revisão por LLM indisponível (só checagem determinística)", tone: "warn" };
    case "handoff":
      return { icon: <ArrowRightLeft className="h-3.5 w-3.5" />, title: "Feedback do Revisor devolvido ao Agente de Operações", detail: (s.input?.feedback ?? []).join(" "), tone: "warn", meta: `revisão ${s.input?.revision}` };
    case "proposal":
      return { icon: <Flag className="h-3.5 w-3.5" />, title: "Plano enviado para a Central de Aprovações (L3)", tone: "brand" };
    case "approval":
      return { icon: <UserCheck className="h-3.5 w-3.5" />, title: s.name === "EXECUTED" ? "Humano aprovou: plano executado" : s.name === "REJECTED" ? "Humano rejeitou" : `Decisão humana: ${s.name}`, tone: s.name === "EXECUTED" ? "ok" : "muted", meta: s.input?.decided_by_role };
    case "run.end":
      return { icon: <CircleDot className="h-3.5 w-3.5" />, title: `Execução finalizada: ${s.name}`, tone: s.name === "DONE" || s.name === "WAITING_APPROVAL" ? "ok" : "danger" };
    default:
      return { icon: <Bot className="h-3.5 w-3.5" />, title: `${s.type} ${s.name}`, tone: "muted" };
  }
}

const toneCls = { brand: "bg-brand-soft text-brand", ok: "bg-ok/10 text-ok", warn: "bg-warn/10 text-warn", danger: "bg-danger/10 text-danger", muted: "bg-muted text-subtle" };

export function Timeline({ steps, dense, live, showRaw }: { steps: Step[]; dense?: boolean; live?: boolean; showRaw?: boolean }) {
  const views = steps.map((s) => ({ s, v: describe(s) })).filter((x) => x.v) as { s: Step; v: StepView }[];
  return (
    <ol className="relative space-y-0">
      {views.map(({ s, v }, i) => (
        <TimelineItem key={`${s.seq}-${i}`} step={s} view={v} dense={dense} last={i === views.length - 1 && !live} showRaw={showRaw} />
      ))}
      {live && (
        <li className="flex items-center gap-3 py-1.5 pl-0.5 text-sm text-subtle">
          <span className="relative flex h-6 w-6 items-center justify-center"><span className="absolute h-3 w-3 animate-ping rounded-full bg-brand/40" /><span className="h-2 w-2 rounded-full bg-brand" /></span>
          trabalhando…
        </li>
      )}
    </ol>
  );
}

function TimelineItem({ step, view, dense, last, showRaw }: { step: Step; view: StepView; dense?: boolean; last: boolean; showRaw?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="relative flex gap-3 pb-3 animate-fade-in">
      {!last && <span className="absolute left-3 top-7 h-[calc(100%-1.25rem)] w-px bg-border" />}
      <span className={cn("z-10 grid h-6 w-6 shrink-0 place-items-center rounded-full", toneCls[view.tone])}>{view.icon}</span>
      <div className="min-w-0 flex-1">
        <button className={cn("flex w-full items-start gap-2 text-left", showRaw && "cursor-pointer")} onClick={() => showRaw && setOpen((o) => !o)}>
          <div className="min-w-0 flex-1">
            <p className={cn("font-medium", dense ? "text-xs" : "text-sm")}>{view.title}</p>
            {view.detail && <p className={cn("mt-0.5 text-subtle break-words", dense ? "text-[11px] line-clamp-2" : "text-xs")}>{view.detail}</p>}
            {view.meta && !dense && <p className="mt-0.5 font-mono text-[11px] text-subtle/80">{view.meta}</p>}
          </div>
          {showRaw && <ChevronDown className={cn("mt-0.5 h-4 w-4 shrink-0 text-subtle transition", open && "rotate-180")} />}
        </button>
        {open && (
          <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-muted p-3 font-mono text-[11px] leading-relaxed scrollbar-thin">
            {JSON.stringify({ input: step.input, output: step.output }, null, 2)}
          </pre>
        )}
      </div>
    </li>
  );
}
