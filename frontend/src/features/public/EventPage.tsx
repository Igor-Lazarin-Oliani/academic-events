import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarDays, CheckCircle2, FileText, MapPin, ShieldAlert, Ticket as TicketIcon } from "lucide-react";
import { api, friendlyError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EventDetail, KnowledgeDoc, Session, Ticket } from "@/lib/types";
import { cn, fmt, initials, KIND_LABEL } from "@/lib/utils";
import { Badge, Button, Card, Dialog, EmptyState, ErrorBox, Skeleton, Tabs, useToast } from "@/components/ui";
import { EventCover, Markdown, Occupancy, SessionBadges, SessionMeta } from "@/components/shared";

export function EventPage() {
  const { slug = "" } = useParams();
  const { user } = useAuth();
  const [tab, setTab] = useState<"programacao" | "palestrantes" | "regulamento">("programacao");
  const { data: ev, isLoading, error } = useQuery({ queryKey: ["event", slug], queryFn: () => api<EventDetail>(`/events/${slug}`) });
  const { data: tickets = [] } = useQuery({ queryKey: ["my-tickets", ev?.id], enabled: !!user && !!ev, queryFn: () => api<Ticket[]>(`/me/tickets?event_id=${ev!.id}`) });

  if (isLoading) return <div className="mx-auto max-w-6xl space-y-4 px-4 py-8"><Skeleton className="h-56" /><Skeleton className="h-96" /></div>;
  if (error || !ev) return <div className="mx-auto max-w-6xl px-4 py-8"><ErrorBox error={error ?? "Evento não encontrado"} /></div>;

  const active = tickets.filter((t) => t.status !== "CANCELLED");
  const capacity = ev.sessions.reduce((a, s) => a + (s.status === "CANCELLED" ? 0 : s.max_capacity), 0);
  const occupied = ev.sessions.reduce((a, s) => a + (s.status === "CANCELLED" ? 0 : s.max_capacity - s.available_spots), 0);

  return (
    <div>
      <EventCover category={ev.category} title={ev.title}>
        <div className="mx-auto max-w-6xl px-4 pb-10 pt-6">
          <Link to="/" className="inline-flex items-center gap-1 text-sm text-white/80 hover:text-white"><ArrowLeft className="h-4 w-4" />Eventos</Link>
          <div className="mt-6 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-3xl font-extrabold sm:text-4xl">{ev.title}</h1>
              <p className="mt-2 max-w-2xl text-white/85">{ev.description}</p>
              <div className="mt-4 flex flex-wrap gap-4 text-sm text-white/90">
                <span className="flex items-center gap-1.5"><CalendarDays className="h-4 w-4" />{fmt.period(ev.start_at, ev.end_at)}</span>
                <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4" />{ev.location}</span>
              </div>
            </div>
            <div className="flex gap-3">
              <div className="rounded-xl bg-white/15 px-4 py-3 text-center backdrop-blur"><p className="text-2xl font-bold">{ev.sessions.length}</p><p className="text-xs text-white/80">sessões</p></div>
              <div className="rounded-xl bg-white/15 px-4 py-3 text-center backdrop-blur"><p className="text-2xl font-bold">{capacity - occupied}</p><p className="text-xs text-white/80">vagas abertas</p></div>
              {user && <Link to="/meus-ingressos" className="rounded-xl bg-white px-4 py-3 text-center text-brand"><p className="text-2xl font-bold">{active.length}</p><p className="text-xs">suas inscrições</p></Link>}
            </div>
          </div>
        </div>
      </EventCover>

      <div className="mx-auto max-w-6xl px-4 py-8">
        <Tabs value={tab} onChange={setTab} className="mb-6" items={[
          { value: "programacao", label: "Programação" },
          { value: "palestrantes", label: "Palestrantes", count: ev.speakers.length },
          { value: "regulamento", label: "Regulamento e FAQ" },
        ]} />
        {tab === "programacao" && <Schedule ev={ev} tickets={tickets} />}
        {tab === "palestrantes" && <Speakers ev={ev} />}
        {tab === "regulamento" && <Rules ev={ev} />}
      </div>
    </div>
  );
}

function Schedule({ ev, tickets }: { ev: EventDetail; tickets: Ticket[] }) {
  const days = useMemo(() => [...new Set(ev.sessions.map((s) => fmt.dayKey(s.start_at)))].sort(), [ev.sessions]);
  const [day, setDay] = useState(days[0]);
  const [kind, setKind] = useState<string>("");
  const bySession = new Map(tickets.filter((t) => t.status !== "CANCELLED").map((t) => [t.session_id, t]));
  const sessions = ev.sessions.filter((s) => fmt.dayKey(s.start_at) === day && (!kind || s.kind === kind));
  return (
    <div>
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
          {days.map((d) => {
            const s = ev.sessions.find((x) => fmt.dayKey(x.start_at) === d)!;
            return (
              <button key={d} onClick={() => setDay(d)} className={cn("min-w-[84px] rounded-xl border px-3 py-2 text-center transition", d === day ? "border-brand bg-brand text-brand-fg" : "border-border bg-surface hover:border-brand/40")}>
                <p className="text-xs capitalize opacity-80">{fmt.weekdayShort(s.start_at)}</p>
                <p className="text-lg font-bold">{fmt.date(s.start_at)}</p>
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {["", "PALESTRA", "MINICURSO", "WORKSHOP", "MESA_REDONDA"].map((k) => (
            <button key={k} onClick={() => setKind(k)} className={cn("rounded-full border px-3 py-1 text-xs font-medium", kind === k ? "border-fg bg-fg text-bg" : "border-border text-subtle hover:text-fg")}>
              {k ? KIND_LABEL[k] : "Todas"}
            </button>
          ))}
        </div>
      </div>
      {sessions.length === 0 ? <EmptyState title="Nenhuma sessão neste filtro" /> : (
        <div className="grid gap-4 md:grid-cols-2">{sessions.map((s) => <SessionCard key={s.id} s={s} ticket={bySession.get(s.id)} eventSlug={ev.slug} />)}</div>
      )}
    </div>
  );
}

function SessionCard({ s, ticket, eventSlug }: { s: Session; ticket?: Ticket; eventSlug: string }) {
  const { user } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const issue = useMutation({
    mutationFn: () => api<Ticket>("/tickets", { body: { session_id: s.id, ticket_id: crypto.randomUUID() } }),
    onSuccess: (t) => {
      toast({ kind: "success", title: "Inscrição confirmada!", description: `${s.code} · ${t.ticket_code}` });
      qc.invalidateQueries({ queryKey: ["event", eventSlug] });
      qc.invalidateQueries({ queryKey: ["my-tickets"] });
      setConfirm(false);
    },
    onError: (e) => toast({ kind: "error", title: "Não foi possível se inscrever", description: friendlyError(e) }),
  });
  const ended = new Date(s.end_at) < new Date();
  return (
    <Card className={cn("flex flex-col p-5", ticket && "ring-2 ring-brand/40")}>
      <div className="flex items-start justify-between gap-3">
        <SessionBadges s={s} />
        <span className="font-mono text-xs text-subtle">{s.code}</span>
      </div>
      <h3 className="mt-3 text-lg font-semibold leading-snug">{s.title}</h3>
      <div className="mt-2"><SessionMeta s={s} /></div>
      <div className="mt-auto flex items-end gap-4 pt-5">
        <Occupancy s={s} />
        {ticket ? (
          <Link to="/meus-ingressos"><Button variant="secondary" size="sm"><CheckCircle2 className="h-4 w-4 text-ok" />Inscrito</Button></Link>
        ) : (
          <Button size="sm" disabled={s.status !== "PUBLISHED" || ended} onClick={() => (user ? setConfirm(true) : nav(`/entrar?next=/eventos/${eventSlug}`))}>
            <TicketIcon className="h-4 w-4" />{s.status === "SOLD_OUT" ? "Esgotado" : ended ? "Encerrada" : "Inscrever-se"}
          </Button>
        )}
      </div>
      <Dialog open={confirm} onClose={() => setConfirm(false)} title="Confirmar inscrição" description={`${s.code} · ${s.title}`}
        footer={<><Button variant="ghost" onClick={() => setConfirm(false)}>Cancelar</Button><Button onClick={() => issue.mutate()} loading={issue.isPending}>Confirmar inscrição</Button></>}>
        <SessionMeta s={s} />
        <p className="mt-4 text-sm text-subtle">Você receberá um ingresso com QR Code. O certificado ({s.workload_hours}h) é emitido para quem fizer check-in na sala.</p>
      </Dialog>
    </Card>
  );
}

function Speakers({ ev }: { ev: EventDetail }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {ev.speakers.map((sp) => {
        const talks = ev.sessions.filter((s) => s.speakers.some((x) => x.id === sp.id));
        return (
          <Card key={sp.id} className="p-5">
            <div className="flex items-center gap-3">
              <span className="grid h-12 w-12 place-items-center rounded-full bg-brand-soft font-bold text-brand">{initials(sp.name)}</span>
              <div><p className="font-semibold">{sp.name}</p><p className="text-sm text-subtle">{sp.affiliation}</p></div>
            </div>
            <p className="mt-3 text-sm text-subtle">{sp.bio}</p>
            <div className="mt-3 space-y-1">{talks.map((t) => <p key={t.id} className="text-xs"><span className="font-mono text-subtle">{t.code}</span> {t.title}</p>)}</div>
          </Card>
        );
      })}
    </div>
  );
}

function Rules({ ev }: { ev: EventDetail }) {
  const { data: docs = [] } = useQuery({ queryKey: ["docs", ev.id], queryFn: () => api<KnowledgeDoc[]>(`/events/${ev.id}/knowledge`) });
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected ?? docs.find((d) => d.trust === "OFFICIAL")?.id ?? null;
  const { data: doc } = useQuery({ queryKey: ["doc", current], enabled: !!current, queryFn: () => api<any>(`/events/${ev.id}/knowledge/${current}`) });
  return (
    <div className="grid gap-6 md:grid-cols-[260px_1fr]">
      <div className="space-y-2">
        {docs.map((d) => (
          <button key={d.id} onClick={() => setSelected(d.id)} className={cn("flex w-full items-start gap-2 rounded-xl border p-3 text-left text-sm transition", d.id === current ? "border-brand bg-brand-soft/50" : "border-border hover:bg-muted")}>
            {d.trust === "OFFICIAL" ? <FileText className="mt-0.5 h-4 w-4 shrink-0 text-brand" /> : <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" />}
            <span><span className="font-medium">{d.title}</span><span className="block text-xs text-subtle">v{d.version} · {d.trust === "OFFICIAL" ? "oficial" : "não verificado"}</span></span>
          </button>
        ))}
      </div>
      <Card className="p-6">
        {doc ? (
          <>
            {doc.trust !== "OFFICIAL" && <Badge tone="warn" className="mb-3"><ShieldAlert className="h-3 w-3" />Documento não verificado: o assistente não o trata como regra oficial</Badge>}
            <Markdown text={doc.content} />
          </>
        ) : <Skeleton className="h-64" />}
      </Card>
    </div>
  );
}
