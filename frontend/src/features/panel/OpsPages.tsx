import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CameraOff, CheckCircle2, Download, Inbox, Search, XCircle } from "lucide-react";
import { api, friendlyError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Attendee, EventDetail, SupportRequest } from "@/lib/types";
import { cn, downloadCsv, fmt, TICKET_STATUS } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, Input, PageHeader, Select, Skeleton, Tabs, Textarea, useToast } from "@/components/ui";
import { usePanelEvent } from "@/components/layout/PanelLayout";

/* ---------------- Inscritos ---------------- */
export function AttendeesPage() {
  const { event } = usePanelEvent();
  const { data: ev } = useQuery({ queryKey: ["event", event!.slug], queryFn: () => api<EventDetail>(`/events/${event!.slug}`) });
  const [session, setSession] = useState("");
  const [q, setQ] = useState("");
  const { user } = useAuth();
  const mustFilter = user?.role === "staff" && !session; // credenciamento só vê uma sessão por vez
  const { data = [], isLoading } = useQuery({
    queryKey: ["attendees", event!.id, session], enabled: !mustFilter,
    queryFn: () => api<Attendee[]>(`/events/${event!.id}/attendees${session ? `?session_id=${session}` : ""}`),
  });
  const rows = data.filter((a) => !q || `${a.participant_name} ${a.participant_email} ${a.ticket_code}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <PageHeader eyebrow="Operação" title="Inscritos" description="Inscrições por sessão, com status de presença."
        actions={<Button variant="outline" onClick={() => downloadCsv(`inscritos-${event!.slug}.csv`, [["Código", "Nome", "E-mail", "Sessão", "Status", "Check-in"], ...rows.map((a) => [a.ticket_code, a.participant_name, a.participant_email, a.session?.code ?? "", TICKET_STATUS[a.status].label, a.checked_in_at ? fmt.dateTime(a.checked_in_at) : ""])])}><Download className="h-4 w-4" />Exportar CSV</Button>} />
      <Card>
        <CardHeader title={`${rows.length} inscrição(ões)`} action={
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-subtle" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nome, e-mail ou código" className="h-9 pl-9 sm:w-64" /></div>
            <Select value={session} onChange={(e) => setSession(e.target.value)} className="h-9 sm:w-72"><option value="">Todas as sessões</option>{ev?.sessions.map((s) => <option key={s.id} value={s.id}>{s.code} · {s.title}</option>)}</Select>
          </div>} />
        <CardBody className="overflow-x-auto">
          {mustFilter ? <EmptyState title="Selecione uma sessão" description="O credenciamento consulta os inscritos sessão por sessão." /> : isLoading ? <Skeleton className="h-64" /> : rows.length === 0 ? <EmptyState title="Nenhuma inscrição" /> : (
            <table className="w-full min-w-[720px] text-sm">
              <thead><tr className="text-left text-xs text-subtle"><th className="pb-2">Participante</th><th className="pb-2">Sessão</th><th className="pb-2">Código</th><th className="pb-2">Status</th><th className="pb-2 text-right">Inscrito em</th></tr></thead>
              <tbody className="divide-y divide-border">
                {rows.slice(0, 300).map((a) => (
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
          {rows.length > 300 && <p className="mt-3 text-xs text-subtle">Mostrando 300 de {rows.length}. Use os filtros ou exporte o CSV.</p>}
        </CardBody>
      </Card>
    </div>
  );
}

/* ---------------- Check-in ---------------- */
declare global { interface Window { BarcodeDetector?: any } }

export function CheckinPage() {
  const { event } = usePanelEvent();
  const [code, setCode] = useState("");
  const [last, setLast] = useState<{ ok: boolean; title: string; detail: string } | null>(null);
  const [history, setHistory] = useState<{ ok: boolean; title: string; detail: string; at: string }[]>([]);
  const [camera, setCamera] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const busy = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const supported = typeof window !== "undefined" && !!window.BarcodeDetector;

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
      setTimeout(() => { busy.current = false; }, 1500);
      inputRef.current?.focus();
    }
  }

  useEffect(() => {
    if (!camera || !supported) return;
    let stream: MediaStream | null = null, raf = 0, stop = false;
    const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then((s) => {
      stream = s;
      if (video.current) { video.current.srcObject = s; video.current.play(); }
      const tick = async () => {
        if (stop || !video.current) return;
        try { const codes = await detector.detect(video.current); if (codes[0]?.rawValue) await checkin(codes[0].rawValue); } catch { /* frame ainda não pronto */ }
        raf = requestAnimationFrame(tick);
      };
      tick();
    }).catch(() => setCamera(false));
    return () => { stop = true; cancelAnimationFrame(raf); stream?.getTracks().forEach((t) => t.stop()); };
  }, [camera]);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="Credenciamento" title="Check-in" description="Leia o QR Code do ingresso ou digite o código. A presença garante o certificado." />
      <Card className="p-5">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); checkin(code); }}>
          <Input ref={inputRef} autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder="EVT-2026-XXXXXX" className="h-12 font-mono text-lg uppercase tracking-wider" />
          <Button type="submit" size="lg">Registrar</Button>
          {supported && <Button type="button" size="lg" variant="outline" onClick={() => setCamera((c) => !c)} aria-label="Câmera">{camera ? <CameraOff className="h-5 w-5" /> : <Camera className="h-5 w-5" />}</Button>}
        </form>
        {camera && <video ref={video} className="mt-4 aspect-video w-full rounded-xl bg-black object-cover" muted playsInline />}
        {!supported && <p className="mt-2 text-xs text-subtle">Leitura por câmera disponível no Chrome/Edge (BarcodeDetector). Leitores USB funcionam como teclado neste campo.</p>}
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
  const { data = [], isLoading } = useQuery({ queryKey: ["support"], queryFn: () => api<SupportRequest[]>("/support-requests"), refetchInterval: 20_000 });
  const rows = data.filter((r) => r.event_id === event!.id && (tab === "OPEN" ? r.status === "OPEN" : r.status !== "OPEN"));
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader eyebrow="Escalonamento" title="Chamados" description="Pedidos que o assistente encaminhou à comissão porque não podia resolver sozinho (exceções, pedidos especiais, informações que não estão no regulamento)." />
      <Tabs value={tab} onChange={setTab} className="mb-4" items={[{ value: "OPEN", label: "Abertos", count: data.filter((r) => r.event_id === event!.id && r.status === "OPEN").length }, { value: "ANSWERED", label: "Respondidos" }]} />
      {isLoading ? <Skeleton className="h-40" /> : rows.length === 0 ? <EmptyState icon={<Inbox className="h-8 w-8" />} title="Nenhum chamado" /> : <div className="space-y-4">{rows.map((r) => <SupportItem key={r.id} r={r} />)}</div>}
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
