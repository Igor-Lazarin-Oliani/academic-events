import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Bot, CheckSquare, Gauge, ShieldAlert, Siren, Ticket, UserCheck, Users } from "lucide-react";
import { api } from "@/lib/api";
import type { Page, Proposal, Run } from "@/lib/types";
import { fmt, plural } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, PageHeader, Progress, Skeleton, Stat } from "@/components/ui";
import { usePanelEvent } from "@/components/layout/PanelLayout";
import { RunStatusBadge } from "./RunsPage";

export function DashboardPage() {
  const { event } = usePanelEvent();
  const id = event!.id;
  const { data: d } = useQuery({ queryKey: ["dashboard", id], queryFn: () => api<any>(`/events/${id}/dashboard`), refetchInterval: 20_000 });
  const { data: stats } = useQuery({ queryKey: ["run-stats", id], queryFn: () => api<any>(`/runs/stats?event_id=${id}`) });
  const { data: pendingPage } = useQuery({ queryKey: ["proposals", "pending", id], queryFn: () => api<Page<Proposal>>(`/proposals?status=PENDING&kind=ACTION_PLAN&event_id=${id}`) });
  const { data: runsPage } = useQuery({ queryKey: ["runs", id, "recent"], queryFn: () => api<Page<Run>>(`/runs?event_id=${id}&limit=6`) });
  const pending = pendingPage?.items ?? [];
  const pendingTotal = pendingPage?.total ?? 0;
  const runs = runsPage?.items ?? [];

  if (!d) return <div className="grid gap-4 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>;
  const chart = d.sessions.filter((s: any) => s.status !== "CANCELLED").map((s: any) => ({ code: s.code, inscritos: s.occupied, livres: s.capacity - s.occupied, title: s.title }));
  const guard = Object.values(stats?.guardrail_events ?? {}).reduce((a: number, b: any) => a + b, 0) as number;

  return (
    <div>
      <PageHeader eyebrow="Visão geral" title={event!.title} description={`${fmt.period(event!.start_at, event!.end_at)} · ${event!.location}`}
        actions={<Link to="/painel/ocorrencias"><Button><Siren className="h-4 w-4" />Relatar ocorrência</Button></Link>} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Participantes" value={d.participants} hint={plural(d.tickets.confirmed + d.tickets.checked_in, "inscrição ativa", "inscrições ativas")} icon={<Users className="h-4 w-4" />} />
        <Stat label="Ocupação" value={`${Math.round(d.occupancy_rate * 100)}%`} hint={`${d.occupied} de ${plural(d.capacity, "vaga", "vagas")} · ${plural(d.sold_out_sessions, "esgotada", "esgotadas")}`} icon={<Gauge className="h-4 w-4" />} tone="accent" />
        <Stat label="Check-ins" value={d.tickets.checked_in} hint={plural(d.tickets.cancelled, "cancelamento", "cancelamentos")} icon={<UserCheck className="h-4 w-4" />} tone="ok" />
        <Stat label="Aguardando aprovação" value={pendingTotal} hint="planos de ação dos agentes" icon={<CheckSquare className="h-4 w-4" />} tone={pendingTotal ? "warn" : "muted"} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader title="Inscrições por sessão" description="Inscritos e vagas livres" />
          <CardBody className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart} margin={{ left: -20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--border))" vertical={false} />
                <XAxis dataKey="code" tick={{ fontSize: 11, fill: "rgb(var(--subtle))" }} />
                <YAxis tick={{ fontSize: 11, fill: "rgb(var(--subtle))" }} />
                <Tooltip contentStyle={{ background: "rgb(var(--surface))", border: "1px solid rgb(var(--border))", borderRadius: 12, fontSize: 12 }}
                  labelFormatter={(code) => chart.find((c: any) => c.code === code)?.title ?? code} />
                <Bar dataKey="inscritos" stackId="a" fill="rgb(var(--brand))" radius={[0, 0, 0, 0]} />
                <Bar dataKey="livres" stackId="a" fill="rgb(var(--brand) / 0.18)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Agentes" description="Execuções neste evento" action={<Link to="/painel/trajetorias"><Button size="sm" variant="ghost">Ver todas</Button></Link>} />
          <CardBody>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl bg-muted p-3"><p className="text-xl font-bold">{stats?.runs ?? 0}</p><p className="text-xs text-subtle">execuções</p></div>
              <div className="rounded-xl bg-muted p-3"><p className="text-xl font-bold">{stats?.latency_s?.p50 ?? "—"}s</p><p className="text-xs text-subtle">latência p50</p></div>
              <div className="rounded-xl bg-muted p-3"><p className="text-xl font-bold">{guard}</p><p className="text-xs text-subtle">guardrails</p></div>
            </div>
            <div className="mt-4 space-y-2">
              {runs.length === 0 && <p className="text-sm text-subtle">Nenhuma execução ainda.</p>}
              {runs.map((r) => (
                <Link key={r.id} to={`/painel/trajetorias/${r.id}`} className="flex items-center gap-3 rounded-xl p-2 hover:bg-muted">
                  <Bot className="h-4 w-4 shrink-0 text-subtle" />
                  <div className="min-w-0 flex-1"><p className="truncate text-sm">{r.input}</p><p className="text-xs text-subtle">{r.agent} · {fmt.relative(r.started_at)}</p></div>
                  <RunStatusBadge status={r.status} />
                </Link>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_1.6fr]">
        <Card>
          <CardHeader title="Aprovações pendentes" action={<Link to="/painel/aprovacoes"><Button size="sm" variant="ghost">Abrir central</Button></Link>} />
          <CardBody>
            {pending.length === 0 ? <EmptyState icon={<CheckSquare className="h-6 w-6" />} title="Tudo em dia" description="Nenhum plano aguardando decisão." /> : (
              <div className="space-y-3">
                {pending.map((p) => (
                  <Link key={p.id} to="/painel/aprovacoes" className="block rounded-xl border border-warn/40 bg-warn/5 p-3 hover:bg-warn/10">
                    <p className="text-sm font-medium">{p.title}</p>
                    <p className="mt-1 text-xs text-subtle">{plural(p.impact?.recipients ?? 0, "inscrito será notificado", "inscritos serão notificados")} · {fmt.relative(p.created_at)}</p>
                  </Link>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Programação" description={d.unavailable_rooms.length ? <span className="flex items-center gap-1 text-warn"><ShieldAlert className="h-3.5 w-3.5" />Salas indisponíveis: {d.unavailable_rooms.join(", ")}</span> : "Ocupação e presença por sessão"} />
          <CardBody className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead><tr className="text-left text-xs text-subtle"><th className="pb-2">Sessão</th><th className="pb-2">Quando</th><th className="pb-2">Sala</th><th className="pb-2 w-40">Ocupação</th><th className="pb-2 text-right">Check-in</th></tr></thead>
              <tbody className="divide-y divide-border">
                {d.sessions.map((s: any) => (
                  <tr key={s.id} className={s.status === "CANCELLED" ? "opacity-50" : ""}>
                    <td className="py-2 pr-2"><span className="font-mono text-xs text-subtle">{s.code}</span> <span className="font-medium">{s.title}</span>{s.status === "SOLD_OUT" && <Badge tone="danger" className="ml-2">esgotada</Badge>}{s.status === "CANCELLED" && <Badge className="ml-2">cancelada</Badge>}</td>
                    <td className="py-2 pr-2 whitespace-nowrap text-subtle">{fmt.weekdayShort(s.start_at)} {fmt.range(s.start_at, s.end_at)}</td>
                    <td className="py-2 pr-2 text-subtle">{s.room}</td>
                    <td className="py-2 pr-2"><div className="flex items-center gap-2"><Progress value={s.occupied / s.capacity} /><span className="w-14 text-right text-xs tabular-nums text-subtle">{s.occupied}/{s.capacity}</span></div></td>
                    <td className="py-2 text-right tabular-nums">{s.checked_in}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      </div>
      <p className="mt-6 flex items-center gap-1.5 text-xs text-subtle"><Ticket className="h-3.5 w-3.5" />Atualizado automaticamente a cada 20 s.</p>
    </div>
  );
}
