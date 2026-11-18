import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, CheckSquare, FileCheck2, Route, ShieldCheck, Users, XCircle } from "lucide-react";
import { api, friendlyError } from "@/lib/api";
import type { Proposal } from "@/lib/types";
import { cn, fmt } from "@/lib/utils";
import { Badge, Button, Card, CardBody, Dialog, EmptyState, PageHeader, Skeleton, Tabs, Textarea, useToast } from "@/components/ui";
import { usePanelEvent } from "@/components/layout/PanelLayout";
import { Markdown } from "@/components/shared";

export function PlanSteps({ changes }: { changes: any[] }) {
  if (!changes?.length) return null;
  return (
    <div className="space-y-2">
      {changes.map((c, i) => (
        <div key={i} className="rounded-xl border border-border p-3">
          <p className="text-sm font-medium">{c.session ? `${c.session}${c.title ? ` · ${c.title}` : ""}` : c.room}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            {c.before && <span className="rounded-lg bg-danger/10 px-2 py-1 text-danger line-through decoration-danger/50">{c.before}</span>}
            {c.before && <ArrowRight className="h-3.5 w-3.5 text-subtle" />}
            <span className="rounded-lg bg-ok/10 px-2 py-1 font-medium text-ok">{c.after}</span>
            {c.tickets_cancelled !== undefined && <Badge tone="danger">{c.tickets_cancelled} inscrições canceladas</Badge>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ReviewBox({ review }: { review: any }) {
  if (!review) return null;
  const det = review.deterministic_issues ?? [];
  const llm = review.llm ?? {};
  return (
    <div className={cn("rounded-xl border p-4", review.approved ? "border-ok/30 bg-ok/5" : "border-warn/40 bg-warn/5")}>
      <p className="flex items-center gap-2 text-sm font-semibold">
        {review.approved ? <ShieldCheck className="h-4 w-4 text-ok" /> : <FileCheck2 className="h-4 w-4 text-warn" />}
        Parecer do Agente Revisor: {review.approved ? "aprovado" : "com pendências"}
      </p>
      <ul className="mt-2 space-y-1 text-xs text-subtle">
        <li>• Checagem determinística (datas, horários, salas, sessões): {det.length ? <span className="text-warn">{det.join("; ")}</span> : "tudo confere com o plano validado"}</li>
        <li>• Avaliação do LLM (clareza, completude, promessas): {llm.skipped ? "indisponível, valeu só a checagem determinística" : llm.approved ? "aprovado" : (llm.issues ?? []).join("; ")}</li>
        {(review.suggestions ?? []).length > 0 && <li>• Sugestões: {review.suggestions.join("; ")}</li>}
      </ul>
    </div>
  );
}

export function ApprovalsPage() {
  const { event } = usePanelEvent();
  const [tab, setTab] = useState<"PENDING" | "history">("PENDING");
  const { data = [], isLoading } = useQuery({ queryKey: ["proposals", "plans", event!.id], queryFn: () => api<Proposal[]>(`/proposals?kind=ACTION_PLAN&event_id=${event!.id}`), refetchInterval: 15_000 });
  const pending = data.filter((p) => p.status === "PENDING");
  const history = data.filter((p) => p.status !== "PENDING");
  return (
    <div>
      <PageHeader eyebrow="Human-in-the-loop (L3)" title="Central de Aprovações" description="Planos propostos pelo Agente de Operações, já validados pelo sistema (dry-run) e conferidos pelo Revisor. Ao aprovar, o sistema executa os passos de forma determinística, tudo ou nada, e notifica os inscritos." />
      <Tabs value={tab} onChange={setTab} className="mb-5" items={[{ value: "PENDING", label: "Pendentes", count: pending.length }, { value: "history", label: "Histórico", count: history.length }]} />
      {isLoading ? <Skeleton className="h-64" /> : (tab === "PENDING" ? pending : history).length === 0 ? (
        <EmptyState icon={<CheckSquare className="h-8 w-8" />} title={tab === "PENDING" ? "Nenhum plano aguardando decisão" : "Nenhuma decisão ainda"}
          action={tab === "PENDING" && <Link to="/painel/ocorrencias"><Button variant="outline">Relatar ocorrência</Button></Link>} />
      ) : (
        <div className="space-y-5">{(tab === "PENDING" ? pending : history).map((p) => <ProposalItem key={p.id} p={p} />)}</div>
      )}
    </div>
  );
}

function ProposalItem({ p }: { p: Proposal }) {
  const [decision, setDecision] = useState<"approve" | "reject" | null>(null);
  const [note, setNote] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({
    mutationFn: (action: "approve" | "reject") => api<Proposal>(`/proposals/${p.id}/${action}`, { body: { note: note || null } }),
    onSuccess: (r) => {
      setDecision(null);
      qc.invalidateQueries({ queryKey: ["proposals"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (r.status === "EXECUTED") toast({ kind: "success", title: "Plano executado", description: `${r.result?.steps?.find((s: any) => s.type === "NOTIFY_PARTICIPANTS")?.recipients ?? 0} inscritos notificados` });
      else if (r.status === "FAILED") toast({ kind: "error", title: "Execução falhou, nada foi aplicado", description: r.error ?? "" });
      else toast({ kind: "info", title: "Plano rejeitado" });
    },
    onError: (e) => toast({ kind: "error", title: "Erro", description: friendlyError(e) }),
  });
  const imp = p.impact ?? {};
  const statusTone = { PENDING: "warn", EXECUTED: "ok", REJECTED: "muted", FAILED: "danger", APPROVED: "brand" }[p.status] as any;
  return (
    <Card className={cn(p.status === "PENDING" && "ring-1 ring-warn/40")}>
      <CardBody className="pt-5">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2"><Badge tone={statusTone}>{p.status}</Badge><Badge tone="muted">L3 · organizador</Badge>{imp.revisions > 0 && <Badge tone="warn">{imp.revisions} revisão(ões)</Badge>}</div>
            <h3 className="mt-2 text-lg font-semibold">{p.title}</h3>
            <p className="mt-1 whitespace-pre-line text-sm text-subtle">{p.summary}</p>
          </div>
          <div className="flex items-center gap-2 rounded-xl bg-muted px-4 py-3"><Users className="h-5 w-5 text-brand" /><div><p className="text-xl font-bold">{imp.recipients ?? 0}</p><p className="text-xs text-subtle">serão notificados</p></div></div>
        </div>
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-subtle">O que muda</p>
            <PlanSteps changes={imp.changes ?? []} />
            {p.payload?.incident && <p className="mt-3 text-xs text-subtle"><span className="font-medium">Ocorrência relatada:</span> “{p.payload.incident}”</p>}
          </div>
          <div className="space-y-3">
            {p.communication && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-subtle">Comunicado aos inscritos</p>
                <div className="rounded-xl border border-border bg-muted/40 p-4"><p className="text-sm font-semibold">{p.communication.title}</p><div className="mt-1 text-sm"><Markdown text={p.communication.body} compact /></div></div>
              </div>
            )}
            <ReviewBox review={p.review} />
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4">
          {p.run_id && <Link to={`/painel/trajetorias/${p.run_id}`}><Button variant="ghost" size="sm"><Route className="h-4 w-4" />Ver trajetória do agente</Button></Link>}
          <span className="text-xs text-subtle">proposto {fmt.relative(p.created_at)}{p.decided_at && ` · decidido ${fmt.relative(p.decided_at)}`}{p.decision_note && ` · “${p.decision_note}”`}</span>
          {p.error && <span className="text-xs text-danger">Erro: {p.error}</span>}
          {p.status === "PENDING" && (
            <div className="ml-auto flex gap-2">
              <Button variant="outline" onClick={() => setDecision("reject")}><XCircle className="h-4 w-4" />Rejeitar</Button>
              <Button variant="success" onClick={() => setDecision("approve")}><CheckCircle2 className="h-4 w-4" />Aprovar e executar</Button>
            </div>
          )}
        </div>
      </CardBody>
      <Dialog open={!!decision} onClose={() => setDecision(null)} title={decision === "approve" ? "Aprovar e executar o plano?" : "Rejeitar o plano?"}
        description={decision === "approve" ? `As mudanças serão aplicadas e ${imp.recipients ?? 0} inscritos receberão o comunicado.` : "Nada será alterado."}
        footer={<><Button variant="ghost" onClick={() => setDecision(null)}>Voltar</Button><Button variant={decision === "approve" ? "success" : "danger"} loading={m.isPending} onClick={() => m.mutate(decision!)}>{decision === "approve" ? "Aprovar e executar" : "Rejeitar"}</Button></>}>
        <Textarea placeholder="Observação (opcional, fica na auditoria)" value={note} onChange={(e) => setNote(e.target.value)} />
      </Dialog>
    </Card>
  );
}
