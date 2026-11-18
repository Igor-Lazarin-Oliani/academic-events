import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, Coins, Cpu, Route, Timer, Wrench } from "lucide-react";
import { api } from "@/lib/api";
import type { Run, RunDetail } from "@/lib/types";
import { fmt } from "@/lib/utils";
import { Badge, Card, CardBody, CardHeader, EmptyState, ErrorBox, PageHeader, Select, Skeleton, Stat } from "@/components/ui";
import { usePanelEvent } from "@/components/layout/PanelLayout";
import { Timeline } from "@/features/assistant/timeline";

const STATUS_TONE: Record<string, any> = { DONE: "ok", WAITING_APPROVAL: "warn", RUNNING: "brand", DEGRADED: "danger", FAILED: "danger", BUDGET_EXCEEDED: "danger", CANCELLED: "muted" };
const AGENT_LABEL: Record<string, string> = { participant: "Assistente", operations: "Operações", reviewer: "Revisor" };

export function RunStatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "muted"}>{status === "WAITING_APPROVAL" ? "aguardando aprovação" : status.toLowerCase()}</Badge>;
}

export function RunsPage() {
  const { event } = usePanelEvent();
  const [agent, setAgent] = useState("");
  const [status, setStatus] = useState("");
  const qs = new URLSearchParams({ event_id: event!.id, limit: "100", ...(agent && { agent }), ...(status && { status }) });
  const { data: runs = [], isLoading } = useQuery({ queryKey: ["runs", qs.toString()], queryFn: () => api<Run[]>(`/runs?${qs}`), refetchInterval: 15_000 });
  const { data: stats } = useQuery({ queryKey: ["run-stats", event!.id], queryFn: () => api<any>(`/runs/stats?event_id=${event!.id}`) });
  return (
    <div>
      <PageHeader eyebrow="Observabilidade" title="Trajetórias dos agentes" description="Cada execução registra a trajetória completa (modelo, ferramentas, guardrails, transições e decisões humanas) para responder “por que o sistema chegou a esta decisão?”." />
      {stats && (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Execuções" value={stats.runs} hint={Object.entries(stats.by_agent_status).map(([a, s]: any) => `${AGENT_LABEL[a] ?? a}: ${Object.values(s).reduce((x: any, y: any) => x + y, 0)}`).join(" · ")} icon={<Bot className="h-4 w-4" />} />
          <Stat label="Latência" value={`${stats.latency_s?.p50 ?? "—"} s`} hint={`p95 ${stats.latency_s?.p95 ?? "—"} s`} icon={<Timer className="h-4 w-4" />} tone="accent" />
          <Stat label="Chamadas" value={stats.model_calls} hint={`${stats.tool_calls} ferramentas · taxa de erro ${(stats.tool_error_rate * 100).toFixed(1)}%`} icon={<Cpu className="h-4 w-4" />} tone="ok" />
          <Stat label="Tokens" value={(stats.tokens_in + stats.tokens_out).toLocaleString("pt-BR")} hint={`${Object.entries(stats.guardrail_events).map(([k, v]) => `${k}: ${v}`).join(" · ") || "nenhum guardrail acionado"}`} icon={<Coins className="h-4 w-4" />} tone="muted" />
        </div>
      )}
      <Card>
        <CardHeader title="Execuções" action={
          <div className="flex gap-2">
            <Select value={agent} onChange={(e) => setAgent(e.target.value)} className="h-9 w-36"><option value="">Todos os agentes</option><option value="participant">Assistente</option><option value="operations">Operações</option><option value="reviewer">Revisor</option></Select>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 w-40"><option value="">Todos os status</option>{Object.keys(STATUS_TONE).map((s) => <option key={s} value={s}>{s}</option>)}</Select>
          </div>} />
        <CardBody className="overflow-x-auto">
          {isLoading ? <Skeleton className="h-40" /> : runs.length === 0 ? <EmptyState icon={<Route className="h-6 w-6" />} title="Nenhuma execução" description="Converse com o assistente ou relate uma ocorrência." /> : (
            <table className="w-full min-w-[720px] text-sm">
              <thead><tr className="text-left text-xs text-subtle"><th className="pb-2">Entrada</th><th className="pb-2">Agente</th><th className="pb-2">Status</th><th className="pb-2 text-right">Modelo/Tools</th><th className="pb-2 text-right">Tokens</th><th className="pb-2 text-right">Duração</th><th className="pb-2 text-right">Quando</th></tr></thead>
              <tbody className="divide-y divide-border">
                {runs.map((r) => (
                  <tr key={r.id} className="hover:bg-muted/50">
                    <td className="max-w-xs py-2.5 pr-3"><Link to={`/painel/trajetorias/${r.id}`} className="line-clamp-1 font-medium hover:text-brand">{r.input || "—"}</Link></td>
                    <td className="py-2.5 pr-3">{AGENT_LABEL[r.agent] ?? r.agent}</td>
                    <td className="py-2.5 pr-3"><RunStatusBadge status={r.status} /></td>
                    <td className="py-2.5 pr-3 text-right tabular-nums">{r.model_calls} / {r.tool_calls}</td>
                    <td className="py-2.5 pr-3 text-right tabular-nums">{(r.tokens_in + r.tokens_out).toLocaleString("pt-BR")}</td>
                    <td className="py-2.5 pr-3 text-right tabular-nums">{r.ended_at ? fmt.duration(new Date(r.ended_at).getTime() - new Date(r.started_at).getTime()) : "—"}</td>
                    <td className="py-2.5 text-right text-subtle">{fmt.relative(r.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

export function RunDetailPage() {
  const { id = "" } = useParams();
  const { data: run, error, isLoading } = useQuery({ queryKey: ["run", id], queryFn: () => api<RunDetail>(`/runs/${id}`), refetchInterval: (q) => (q.state.data?.status === "RUNNING" ? 2000 : false) });
  if (isLoading) return <Skeleton className="h-96" />;
  if (error || !run) return <ErrorBox error={error ?? "Execução não encontrada"} />;
  const ctx = run.steps.find((s) => s.type === "run.start")?.output?.context;
  const tools = run.steps.filter((s) => s.type === "tool.result");
  const guards = run.steps.filter((s) => s.type === "guardrail" && s.status !== "passed");
  return (
    <div>
      <Link to="/painel/trajetorias" className="mb-4 inline-flex items-center gap-1 text-sm text-subtle hover:text-fg"><ArrowLeft className="h-4 w-4" />Trajetórias</Link>
      <PageHeader eyebrow={`${AGENT_LABEL[run.agent] ?? run.agent} · ${fmt.dateTime(run.started_at)}`} title={<span className="line-clamp-2">{run.input}</span>}
        actions={<RunStatusBadge status={run.status} />} />
      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader title="Trajetória" description="Clique em um passo para ver entrada e saída (dados pessoais mascarados)" />
          <CardBody><Timeline steps={run.steps} showRaw /></CardBody>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Resumo" />
            <CardBody className="grid grid-cols-2 gap-3 text-sm">
              <Metric icon={<Cpu className="h-4 w-4" />} label="Chamadas ao modelo" value={run.model_calls} />
              <Metric icon={<Wrench className="h-4 w-4" />} label="Ferramentas" value={`${run.tool_calls} (${tools.filter((t) => t.status !== "ok").length} erro)`} />
              <Metric icon={<Coins className="h-4 w-4" />} label="Tokens" value={(run.tokens_in + run.tokens_out).toLocaleString("pt-BR")} />
              <Metric icon={<Timer className="h-4 w-4" />} label="Duração" value={run.ended_at ? fmt.duration(new Date(run.ended_at).getTime() - new Date(run.started_at).getTime()) : "em andamento"} />
              <div className="col-span-2 text-xs text-subtle">correlation_id <span className="font-mono">{run.correlation_id}</span>{run.current_node && <> · nó atual <span className="font-mono">{run.current_node}</span></>}</div>
              {run.error && <div className="col-span-2 rounded-lg bg-danger/5 p-2 text-xs text-danger">{run.error}</div>}
            </CardBody>
          </Card>
          {guards.length > 0 && (
            <Card>
              <CardHeader title="Guardrails acionados" />
              <CardBody className="space-y-1.5">{guards.map((g) => <div key={g.seq} className="flex items-center justify-between text-sm"><span className="font-mono text-xs">{g.name}</span><Badge tone={g.status === "flagged" ? "warn" : "danger"}>{g.status}</Badge></div>)}</CardBody>
            </Card>
          )}
          {ctx && (
            <Card>
              <CardHeader title="Contrato de contexto" description="O que o modelo recebeu além da mensagem" />
              <CardBody><pre className="max-h-96 overflow-auto rounded-lg bg-muted p-3 font-mono text-[11px] scrollbar-thin">{JSON.stringify(ctx, null, 2)}</pre></CardBody>
            </Card>
          )}
          {run.state && Object.keys(run.state).length > 0 && (
            <Card>
              <CardHeader title="Checkpoint (estado do grafo)" />
              <CardBody><pre className="max-h-96 overflow-auto rounded-lg bg-muted p-3 font-mono text-[11px] scrollbar-thin">{JSON.stringify(run.state, null, 2)}</pre></CardBody>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return <div className="rounded-xl bg-muted p-3"><p className="flex items-center gap-1.5 text-xs text-subtle">{icon}{label}</p><p className="mt-1 font-semibold">{value}</p></div>;
}
