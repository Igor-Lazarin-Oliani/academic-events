import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Award, Inbox, MessageSquareText, Ticket as TicketIcon } from "lucide-react";
import { api, friendlyError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Page, Proposal, SupportRequest, Ticket } from "@/lib/types";
import { cn, fmt, pluralWord, TICKET_STATUS } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, Dialog, EmptyState, PageHeader, Skeleton, Tabs, Textarea, useToast } from "@/components/ui";
import { SessionBadges, SessionMeta } from "@/components/shared";
import { ProposalCard } from "@/features/assistant/ProposalCard";

export function MyTicketsPage() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<"active" | "past">("active");
  const { data: tickets = [], isLoading } = useQuery({ queryKey: ["my-tickets", "all"], enabled: !!user, queryFn: () => api<Ticket[]>("/me/tickets") });
  const { data: proposals = [] } = useQuery({ queryKey: ["my-proposals"], enabled: !!user, queryFn: () => api<Page<Proposal>>("/proposals?status=PENDING"), select: (p) => p.items });
  const { data: requests = [] } = useQuery({ queryKey: ["my-requests"], enabled: !!user, queryFn: () => api<SupportRequest[]>("/me/support-requests") });
  if (loading) return null;
  if (!user) return <Navigate to="/entrar?next=/meus-ingressos" replace />;

  const active = tickets.filter((t) => t.status !== "CANCELLED").sort((a, b) => (a.session!.start_at < b.session!.start_at ? -1 : 1));
  const past = tickets.filter((t) => t.status === "CANCELLED");
  const hours = tickets.filter((t) => t.status === "CHECKED_IN").reduce((a, t) => a + (t.session?.workload_hours ?? 0), 0);
  const myL2 = proposals.filter((p) => p.level === "L2" && p.requested_by === user.id);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <PageHeader eyebrow="Minha conta" title="Meus ingressos" description="Informe o código do ingresso na porta da sala para registrar presença e garantir o certificado." />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Card className="flex items-center gap-4 p-5"><TicketIcon className="h-8 w-8 text-brand" /><div><p className="text-2xl font-bold">{active.length}</p><p className="text-sm text-subtle">{pluralWord(active.length, "inscrição ativa", "inscrições ativas")}</p></div></Card>
        <Card className="flex items-center gap-4 p-5"><Award className="h-8 w-8 text-accent" /><div><p className="text-2xl font-bold">{hours}h</p><p className="text-sm text-subtle">com presença registrada</p></div></Card>
        <Card className="flex items-center gap-4 p-5"><MessageSquareText className="h-8 w-8 text-ok" /><div><p className="text-2xl font-bold">{requests.length}</p><p className="text-sm text-subtle">{pluralWord(requests.length, "chamado com a comissão", "chamados com a comissão")}</p></div></Card>
      </div>

      {myL2.length > 0 && (
        <Card className="mb-6">
          <CardHeader title="Aguardando sua confirmação" description="Solicitações preparadas pelo assistente. Nada muda até você confirmar." />
          <CardBody className="grid gap-3 md:grid-cols-2">{myL2.map((p) => <ProposalCard key={p.id} proposal={p} />)}</CardBody>
        </Card>
      )}

      <Tabs value={tab} onChange={setTab} className="mb-4" items={[{ value: "active", label: "Ativos", count: active.length }, { value: "past", label: "Cancelados", count: past.length }]} />
      {isLoading ? <Skeleton className="h-48" /> : (tab === "active" ? active : past).length === 0 ? (
        <EmptyState icon={<TicketIcon className="h-8 w-8" />} title={tab === "active" ? "Você ainda não tem inscrições" : "Nenhum ingresso cancelado"}
          action={tab === "active" && <Link to="/"><Button>Ver eventos</Button></Link>} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">{(tab === "active" ? active : past).map((t) => <TicketCard key={t.id} t={t} />)}</div>
      )}

      {requests.length > 0 && (
        <Card className="mt-8">
          <CardHeader title="Chamados com a comissão" description="Abertos pelo assistente quando ele não pôde resolver." />
          <CardBody className="divide-y divide-border">
            {requests.map((r) => (
              <div key={r.id} className="py-3">
                <div className="flex items-center gap-2"><Inbox className="h-4 w-4 text-subtle" /><p className="text-sm font-medium">{r.summary}</p><Badge tone={r.status === "OPEN" ? "warn" : "ok"} className="ml-auto">{r.status === "OPEN" ? "Aberto" : "Respondido"}</Badge></div>
                {r.answer && <p className="ml-6 mt-1 text-sm text-subtle">↳ {r.answer}</p>}
                <p className="ml-6 mt-1 text-xs text-subtle">{fmt.relative(r.created_at)}</p>
              </div>
            ))}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function TicketCard({ t }: { t: Ticket }) {
  const s = t.session!;
  const [cancel, setCancel] = useState(false);
  const [reason, setReason] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const st = TICKET_STATUS[t.status];
  const mutation = useMutation({
    mutationFn: () => api<Ticket>(`/tickets/${t.id}/cancel`, { body: { reason } }),
    onSuccess: () => { toast({ kind: "success", title: "Inscrição cancelada", description: "A vaga foi liberada." }); qc.invalidateQueries({ queryKey: ["my-tickets"] }); qc.invalidateQueries({ queryKey: ["event"] }); setCancel(false); },
    onError: (e) => toast({ kind: "error", title: "Não foi possível cancelar", description: friendlyError(e) }),
  });
  return (
    <Card className={cn("flex overflow-hidden", t.status === "CANCELLED" && "opacity-70")}>
      <div className="flex-1 p-5">
        <div className="flex items-center gap-2"><Badge tone={st.tone}>{st.label}</Badge><span className="font-mono text-xs text-subtle">{t.ticket_code}</span></div>
        <h3 className="mt-2 font-semibold">{s.code} · {s.title}</h3>
        <div className="mt-2"><SessionMeta s={s} /></div>
        <div className="mt-3"><SessionBadges s={s} /></div>
        {t.status === "CONFIRMED" && (
          <div className="mt-4 flex gap-2">
            <Button size="sm" variant="ghost" className="text-danger" onClick={() => setCancel(true)}>Cancelar inscrição</Button>
          </div>
        )}
        {t.cancel_reason && <p className="mt-3 text-xs text-subtle">Motivo: {t.cancel_reason.startsWith("plan:") ? "sessão cancelada pela comissão" : t.cancel_reason}</p>}
      </div>
      <Dialog open={cancel} onClose={() => setCancel(false)} title="Cancelar inscrição?" description={`${s.code} · ${s.title}`}
        footer={<><Button variant="ghost" onClick={() => setCancel(false)}>Voltar</Button><Button variant="danger" loading={mutation.isPending} onClick={() => mutation.mutate()}>Cancelar inscrição</Button></>}>
        <p className="mb-3 text-sm text-subtle">A vaga volta a ficar disponível para outros participantes imediatamente.</p>
        <Textarea placeholder="Motivo (opcional)" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
      </Dialog>
    </Card>
  );
}
