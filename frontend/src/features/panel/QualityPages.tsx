import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Bot, CheckCircle2, FlaskConical, Layers, ShieldCheck, Wrench, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { Activity } from "@/lib/types";
import { cn, fmt } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorBox, PageHeader, Progress, Select, Skeleton, Stat } from "@/components/ui";
import { usePanelEvent } from "@/components/layout/PanelLayout";

const CATEGORY_LABEL: Record<string, string> = {
  resposta_com_evidencia: "Resposta com evidência", dados_do_usuario: "Dados do usuário", abstencao: "Abstenção (“não sei”)", acesso_negado: "Acesso negado (“não posso”)",
  injecao: "Injeção de instruções", tool_indisponivel: "Ferramenta indisponível", acao_l2: "Ações L2 (propor, não executar)", escalonamento: "Escalonamento",
  plano_de_ocorrencia: "Plano de ocorrência", revisor: "Revisor",
};

/* ---------------- Evals ---------------- */
export function EvalsPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ["evals"], queryFn: () => api<any>("/evals/latest") });
  const [open, setOpen] = useState<string | null>(null);
  if (isLoading) return <Skeleton className="h-96" />;
  if (error) return <div><PageHeader eyebrow="Qualidade" title="Evals" /><EmptyState icon={<FlaskConical className="h-8 w-8" />} title="Nenhum relatório ainda" description={<>Rode <code className="rounded bg-muted px-1">docker compose exec backend python /evals/run.py</code></>} /></div>;
  const rate = data.passed / data.total;
  return (
    <div>
      <PageHeader eyebrow="Qualidade" title="Evals de comportamento" description="Casos executados contra o modelo real, num banco próprio recriado a cada execução. Nada de comparar texto exato: os critérios são fontes citadas, ferramentas chamadas, ausência de efeitos colaterais e oráculos SQL." />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Stat label="Casos aprovados" value={`${data.passed}/${data.total}`} hint={`${Math.round(rate * 100)}% · ${fmt.dateTime(data.generated_at)}`} icon={<CheckCircle2 className="h-4 w-4" />} tone={rate === 1 ? "ok" : "warn"} />
        <Stat label="Latência média" value={`${data.avg_latency_s}s`} hint="por caso, incluindo fallbacks" icon={<FlaskConical className="h-4 w-4" />} tone="accent" />
        <Stat label="Modelos" value={<span className="text-base">{data.model?.GEMINI_MODEL_LIGHT}</span>} hint={`principal ${data.model?.GEMINI_MODEL} · fallback ${data.model?.GEMINI_FALLBACK_MODELS}`} icon={<Bot className="h-4 w-4" />} tone="muted" />
      </div>
      <Card className="mb-6">
        <CardHeader title="Por categoria" />
        <CardBody className="grid gap-x-8 gap-y-3 md:grid-cols-2">
          {Object.entries(data.by_category).map(([k, v]: any) => (
            <div key={k}><div className="mb-1 flex justify-between text-sm"><span>{CATEGORY_LABEL[k] ?? k}</span><span className="tabular-nums text-subtle">{v.passed}/{v.total}</span></div><Progress value={v.passed / v.total} tone={v.passed === v.total ? "ok" : "warn"} /></div>
          ))}
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Casos" />
        <CardBody className="divide-y divide-border">
          {data.results.map((r: any) => (
            <div key={r.id} className="py-3">
              <button className="flex w-full items-center gap-3 text-left" onClick={() => setOpen(open === r.id ? null : r.id)}>
                {r.passed ? <CheckCircle2 className="h-5 w-5 text-ok" /> : <XCircle className="h-5 w-5 text-danger" />}
                <span className="w-10 font-mono text-xs">{r.id}</span>
                <Badge>{CATEGORY_LABEL[r.category] ?? r.category}</Badge>
                <span className="truncate text-sm text-subtle">{r.answer}</span>
                <span className="ml-auto shrink-0 text-xs tabular-nums text-subtle">{r.latency_s}s</span>
              </button>
              {open === r.id && (
                <div className="ml-8 mt-3 space-y-2 text-sm">
                  <div className="flex flex-wrap gap-1.5">{r.checks.map((c: any) => <Badge key={c.check} tone={c.passed ? "ok" : "danger"}>{c.check}</Badge>)}</div>
                  <p className="text-xs text-subtle">status {r.status} · kind {r.kind} · ferramentas: {(r.tools_called ?? []).join(", ") || "—"} · guardrails: {(r.guardrails ?? []).join(", ") || "—"}</p>
                  {r.checks.filter((c: any) => !c.passed).map((c: any) => <p key={c.check} className="text-xs text-danger">{c.check}: {JSON.stringify(c.detail)}</p>)}
                </div>
              )}
            </div>
          ))}
        </CardBody>
      </Card>
    </div>
  );
}

/* ---------------- Arquitetura ---------------- */
const LEVEL_TONE: Record<string, any> = { L0: "ok", L1: "brand", L2: "warn", L3: "danger" };
export function AgentsPage() {
  const { data = [], isLoading } = useQuery({ queryKey: ["agents"], queryFn: () => api<any[]>("/agents") });
  return (
    <div>
      <PageHeader eyebrow="Arquitetura orientada a agentes" title="Agentes, ferramentas e limites" description="O LLM solicita; o sistema autoriza e registra. Cada ferramenta é um contrato tipado com nível de autonomia. Ações L2 e L3 só criam propostas, e a decisão é sempre humana, fora do alcance do agente." />
      <div className="mb-6 grid gap-3 md:grid-cols-4">
        {[["L0", "Leitura", "automático"], ["L1", "Reversível", "automático + log"], ["L2", "Efeito no sistema", "o próprio usuário confirma"], ["L3", "Crítico/coletivo", "organizador aprova"]].map(([l, t, d]) => (
          <Card key={l} className="p-4"><Badge tone={LEVEL_TONE[l]}>{l}</Badge><p className="mt-2 font-semibold">{t}</p><p className="text-sm text-subtle">{d}</p></Card>
        ))}
      </div>
      {isLoading ? <Skeleton className="h-96" /> : (
        <div className="space-y-6">
          {data.map((a) => (
            <Card key={a.name}>
              <CardHeader title={<span className="flex items-center gap-2"><Bot className="h-5 w-5 text-brand" />{a.title}</span>} description={a.goal} action={<Badge tone="brand"><Layers className="h-3 w-3" />{a.pattern}</Badge>} />
              <CardBody>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-xl bg-muted p-3 text-sm"><p className="text-xs font-semibold uppercase text-subtle">Decisão delegada ao modelo</p><p className="mt-1">{a.decides}</p></div>
                  <div className="rounded-xl bg-muted p-3 text-sm"><p className="text-xs font-semibold uppercase text-subtle">Critérios de parada</p><ul className="mt-1 list-disc pl-4">{a.stop.map((s: string) => <li key={s}>{s}</li>)}</ul></div>
                </div>
                {a.tools.length > 0 && (
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full min-w-[640px] text-sm">
                      <thead><tr className="text-left text-xs text-subtle"><th className="pb-2">Ferramenta</th><th className="pb-2">Nível</th><th className="pb-2">Efeito</th><th className="pb-2">Parâmetros</th></tr></thead>
                      <tbody className="divide-y divide-border">
                        {a.tools.map((t: any) => (
                          <tr key={t.name}><td className="py-2 pr-3"><p className="flex items-center gap-1.5 font-mono text-xs font-medium"><Wrench className="h-3 w-3" />{t.name}</p><p className="text-xs text-subtle">{t.description}</p></td>
                            <td className="py-2 pr-3"><Badge tone={LEVEL_TONE[t.level]}>{t.level}</Badge></td><td className="py-2 pr-3 text-xs text-subtle">{t.effect}</td>
                            <td className="py-2 font-mono text-[11px] text-subtle">{Object.keys(t.parameters.properties ?? {}).join(", ") || "—"}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardBody>
            </Card>
          ))}
          <Card className="p-5">
            <p className="flex items-center gap-2 font-semibold"><ShieldCheck className="h-5 w-5 text-ok" />O que nunca é uma ferramenta</p>
            <p className="mt-1 text-sm text-subtle">Aprovar ou rejeitar propostas (<code>POST /proposals/:id/approve</code>), executar planos, enviar notificações e ler dados pessoais de inscritos. Essas operações são código determinístico acionado por humanos.</p>
          </Card>
        </div>
      )}
    </div>
  );
}

/* ---------------- Auditoria ---------------- */
export function AuditPage() {
  const { event } = usePanelEvent();
  const [source, setSource] = useState("");
  const [entity, setEntity] = useState("");
  const qs = new URLSearchParams({ limit: "200", ...(source && { source }), ...(entity && { entity_type: entity }) });
  const { data = [], isLoading, error } = useQuery({ queryKey: ["activity", qs.toString()], queryFn: () => api<Activity[]>(`/activity?${qs}`) });
  const qc = useQueryClient();
  const triage = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => api(`/activity/${id}`, { method: "PUT", body: { status } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["activity"] }) });
  const archive = useMutation({ mutationFn: (id: string) => api(`/activity/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["activity"] }) });
  return (
    <div>
      <PageHeader eyebrow="Auditoria" title="Registro de atividades" description={`Cada mudança (por humanos, pelo sistema ou originada por agentes) gravada na mesma transação, com ator e correlation_id. O fato é imutável; só a triagem muda. ${event?.title ?? ""}`} />
      <Card>
        <CardHeader title={`${data.length} registros`} action={
          <div className="flex gap-2">
            <Select className="h-9 w-36" value={source} onChange={(e) => setSource(e.target.value)}><option value="">Todas as origens</option><option value="agent">Agente</option><option value="api">API (humano)</option><option value="system">Sistema</option></Select>
            <Select className="h-9 w-36" value={entity} onChange={(e) => setEntity(e.target.value)}><option value="">Todas as entidades</option>{["proposal", "session", "ticket", "room", "support_request", "event"].map((x) => <option key={x}>{x}</option>)}</Select>
          </div>} />
        <CardBody className="overflow-x-auto">
          {error ? <ErrorBox error={error} /> : isLoading ? <Skeleton className="h-64" /> : (
            <table className="w-full min-w-[820px] text-sm">
              <thead><tr className="text-left text-xs text-subtle"><th className="pb-2">Quando</th><th className="pb-2">Ação</th><th className="pb-2">Origem</th><th className="pb-2">Detalhe</th><th className="pb-2">Triagem</th><th /></tr></thead>
              <tbody className="divide-y divide-border">
                {data.map((l) => (
                  <tr key={l.id}>
                    <td className="whitespace-nowrap py-2 pr-3 text-subtle">{fmt.dateTime(l.occurred_at)}</td>
                    <td className="py-2 pr-3"><span className="font-mono text-xs">{l.action}</span></td>
                    <td className="py-2 pr-3"><Badge tone={l.source === "agent" ? "brand" : l.source === "system" ? "muted" : "ok"}>{l.source}</Badge>{l.actor_role && <span className="ml-1 text-xs text-subtle">{l.actor_role}</span>}</td>
                    <td className={cn("max-w-sm py-2 pr-3 text-xs", l.level === "ERROR" ? "text-danger" : "text-subtle")}><span className="line-clamp-2">{l.message || JSON.stringify(l.payload).slice(0, 140)}</span></td>
                    <td className="py-2 pr-3"><Select className="h-8 w-32 text-xs" value={l.status} onChange={(e) => triage.mutate({ id: l.id, status: e.target.value })}><option value="NEW">Novo</option><option value="REVIEWED">Revisado</option><option value="RESOLVED">Resolvido</option></Select></td>
                    <td className="py-2"><Button size="icon" variant="ghost" title="Arquivar" onClick={() => archive.mutate(l.id)}><Archive className="h-4 w-4" /></Button></td>
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

