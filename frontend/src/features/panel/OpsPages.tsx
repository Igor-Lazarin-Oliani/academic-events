import { useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, Inbox, Search, XCircle } from "lucide-react";
import { api, apiDownload, friendlyError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { pageQuery, useDebounced, usePagination } from "@/lib/pagination";
import type { Attendee, EventDetail, Page, SupportRequest } from "@/lib/types";
import { cn, fmt, plural, TICKET_STATUS } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, Input, PageHeader, Pagination, Select, Skeleton, Tabs, Textarea, useToast } from "@/components/ui";
import { usePanelEvent } from "@/components/layout/PanelLayout";

/* ---------------- Inscritos ---------------- */
export function AttendeesPage() {
  const { event } = usePanelEvent();
  const { data: ev } = useQuery({ queryKey: ["event", event!.slug], queryFn: () => api<EventDetail>(`/events/${event!.slug}`) });
  const [session, setSession] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const search = useDebounced(q.trim());
  const { user } = useAuth();
  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  const mustFilter = user?.role === "staff" && !session; // credenciamento só vê uma sessão por vez
  // Filtros e busca rodam no servidor; a tela só carrega uma página (50) por vez.
  const filters = pageQuery({ session_id: session, status, q: search }).toString();
  const pg = usePagination(`${event!.id}|${filters}`);
  const qs = pageQuery({ session_id: session, status, q: search }, pg);
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["attendees", event!.id, qs.toString()], enabled: !mustFilter, placeholderData: keepPreviousData,
    queryFn: () => api<Page<Attendee>>(`/events/${event!.id}/attendees?${qs}`),
  });
  const rows = data?.items ?? [];
  const total = data?.total ?? 0;
  async function exportCsv() {
    setExporting(true);
    try { await apiDownload(`/events/${event!.id}/attendees/export?${filters}`, `inscritos-${event!.slug}.csv`); }
    catch (e) { toast({ kind: "error", title: "Não foi possível exportar", description: friendlyError(e) }); }
    finally { setExporting(false); }
  }
  return (
    <div>
      <PageHeader eyebrow="Operação" title="Inscritos" description="Inscrições por sessão, com status de presença."
        actions={<Button variant="outline" onClick={exportCsv} loading={exporting} disabled={mustFilter}><Download className="h-4 w-4" />Exportar CSV</Button>} />
      <Card>
        <CardHeader title={plural(total, "inscrição", "inscrições")} action={
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-subtle" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nome, e-mail ou código" className="h-9 pl-9 sm:w-64" /></div>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 sm:w-44"><option value="">Todos os status</option>{Object.entries(TICKET_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Select>
            <Select value={session} onChange={(e) => setSession(e.target.value)} className="h-9 sm:w-72"><option value="">Todas as sessões</option>{ev?.sessions.map((s) => <option key={s.id} value={s.id}>{s.code} · {s.title}</option>)}</Select>
          </div>} />
        <CardBody className="overflow-x-auto">
          {mustFilter ? <EmptyState title="Selecione uma sessão" description="O credenciamento consulta os inscritos sessão por sessão." /> : isLoading ? <Skeleton className="h-64" /> : rows.length === 0 ? <EmptyState title="Nenhuma inscrição" description={search || status ? "Nenhum resultado para os filtros atuais." : undefined} /> : (
            <table className={cn("w-full min-w-[720px] text-sm transition-opacity", isFetching && "opacity-60")}>
              <thead><tr className="text-left text-xs text-subtle"><th className="pb-2">Participante</th><th className="pb-2">Sessão</th><th className="pb-2">Código</th><th className="pb-2">Status</th><th className="pb-2 text-right">Inscrito em</th></tr></thead>
              <tbody className="divide-y divide-border">
                {rows.map((a) => (
                  <tr key={a.id}>
                    <td className="py-2 pr-3"><p className="font-medium">{a.participant_name}</p><p className="text-xs text-subtle">{a.participant_email}</p></td>
                    <td className="py-2 pr-3"><span className="font-mono text-xs text-subtle">{a.session?.code}</span> {a.session?.title}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{a.ticket_code}</td>
                    <td className="py-2 pr-3"><Badge tone={TICKET_STATUS[a.status].tone}>{TICKET_STATUS[a.status].label}</Badge></td>
                    <td className="py-2 text-right text-subtle">{fmt.dateTime(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!mustFilter && !isLoading && <Pagination page={pg.page} pageSize={pg.pageSize} total={total} onPageChange={pg.setPage} loading={isFetching} />}
        </CardBody>
      </Card>
    </div>
  );
}

/* ---------------- Check-in ---------------- */
export function CheckinPage() {
  const { event } = usePanelEvent();
  const [code, setCode] = useState("");
  const [last, setLast] = useState<{ ok: boolean; title: string; detail: string } | null>(null);
  const [history, setHistory] = useState<{ ok: boolean; title: string; detail: string; at: string }[]>([]);
  const busy = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function checkin(raw: string) {
    const c = raw.trim().toUpperCase();
    if (!c || busy.current) return;
    busy.current = true;
    try {
      const a = await api<Attendee>("/checkin", { body: { code: c, event_id: event!.id } });
      const r = { ok: true, title: a.participant_name, detail: `${a.session?.code} · ${a.session?.title} · ${a.session?.room?.name ?? ""}` };
      setLast(r); setHistory((h) => [{ ...r, at: new Date().toISOString() }, ...h].slice(0, 12));
    } catch (e) {
      const r = { ok: false, title: c, detail: friendlyError(e) };
      setLast(r); setHistory((h) => [{ ...r, at: new Date().toISOString() }, ...h].slice(0, 12));
    } finally {
      setCode("");
      busy.current = false;
      inputRef.current?.focus();
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="Credenciamento" title="Check-in" description="Digite o código do ingresso informado pelo participante. A presença garante o certificado." />
      <Card className="p-5">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); checkin(code); }}>
          <Input ref={inputRef} autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder="EVT-2026-XXXXXX" className="h-12 font-mono text-lg uppercase tracking-wider" />
          <Button type="submit" size="lg">Registrar</Button>
        </form>
      </Card>
      {last && (
        <div className={cn("mt-5 flex items-center gap-4 rounded-2xl p-6 animate-fade-in", last.ok ? "bg-ok text-white" : "bg-danger text-white")}>
          {last.ok ? <CheckCircle2 className="h-12 w-12 shrink-0" /> : <XCircle className="h-12 w-12 shrink-0" />}
          <div><p className="text-2xl font-bold">{last.ok ? "Presença registrada" : "Não autorizado"}</p><p className="mt-1 text-lg">{last.title}</p><p className="text-sm opacity-90">{last.detail}</p></div>
        </div>
      )}
      {history.length > 0 && (
        <Card className="mt-5">
          <CardHeader title="Últimas leituras" />
          <CardBody className="divide-y divide-border">
            {history.map((h, i) => <div key={i} className="flex items-center gap-3 py-2 text-sm">{h.ok ? <CheckCircle2 className="h-4 w-4 text-ok" /> : <XCircle className="h-4 w-4 text-danger" />}<span className="font-medium">{h.title}</span><span className="truncate text-subtle">{h.detail}</span><span className="ml-auto text-xs text-subtle">{fmt.time(h.at)}</span></div>)}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

/* ---------------- Chamados ---------------- */
export function SupportPage() {
  const { event } = usePanelEvent();
  const [tab, setTab] = useState<"OPEN" | "ANSWERED">("OPEN");
  const [q, setQ] = useState("");
  const search = useDebounced(q.trim());
  const status = tab === "OPEN" ? "OPEN" : "ANSWERED,CLOSED";
  const pg = usePagination(`${event!.id}|${tab}|${search}`);
  const qs = pageQuery({ event_id: event!.id, status, q: search }, pg);
  const { data, isLoading, isFetching } = useQuery({ queryKey: ["support", qs.toString()], queryFn: () => api<Page<SupportRequest>>(`/support-requests?${qs}`), refetchInterval: 20_000, placeholderData: keepPreviousData });
  // Contador da aba "Abertos" (só o total, sem trazer os itens).
  const { data: openCount } = useQuery({ queryKey: ["support", "open-count", event!.id], queryFn: () => api<Page<SupportRequest>>(`/support-requests?event_id=${event!.id}&status=OPEN&limit=1`), refetchInterval: 20_000 });
  const rows = data?.items ?? [];
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader eyebrow="Escalonamento" title="Chamados" description="Pedidos que o assistente encaminhou à comissão porque não podia resolver sozinho (exceções, pedidos especiais, informações que não estão no regulamento)." />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={tab} onChange={setTab} items={[{ value: "OPEN", label: "Abertos", count: openCount?.total }, { value: "ANSWERED", label: "Respondidos" }]} />
        <div className="relative"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-subtle" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar no pedido ou na resposta" className="h-9 pl-9 sm:w-72" /></div>
      </div>
      {isLoading ? <Skeleton className="h-40" /> : rows.length === 0 ? <EmptyState icon={<Inbox className="h-8 w-8" />} title="Nenhum chamado" /> : <div className={cn("space-y-4 transition-opacity", isFetching && "opacity-60")}>{rows.map((r) => <SupportItem key={r.id} r={r} />)}</div>}
      {!isLoading && <Pagination page={pg.page} pageSize={pg.pageSize} total={data?.total ?? 0} onPageChange={pg.setPage} loading={isFetching} />}
    </div>
  );
}

function SupportItem({ r }: { r: SupportRequest }) {
  const [answer, setAnswer] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({ mutationFn: () => api(`/support-requests/${r.id}/answer`, { body: { answer } }), onSuccess: () => { toast({ kind: "success", title: "Resposta enviada ao participante" }); qc.invalidateQueries({ queryKey: ["support"] }); } });
  return (
    <Card className="p-5">
      <div className="flex items-start gap-3"><Inbox className="mt-0.5 h-5 w-5 text-brand" /><div className="flex-1"><p className="font-medium">{r.summary}</p><p className="mt-1 text-xs text-subtle">{fmt.relative(r.created_at)}{r.run_id && " · aberto pelo assistente"}</p></div></div>
      {r.answer ? <p className="ml-8 mt-3 rounded-xl bg-muted p-3 text-sm">{r.answer}</p> : (
        <div className="ml-8 mt-3 flex flex-col gap-2 sm:flex-row"><Textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Resposta para o participante (vira notificação)" className="min-h-[44px]" /><Button onClick={() => m.mutate()} loading={m.isPending} disabled={answer.length < 3}>Responder</Button></div>
      )}
    </Card>
  );
}
