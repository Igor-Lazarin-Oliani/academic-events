import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, MapPin, Search, ShieldCheck, Sparkles, Users } from "lucide-react";
import { api } from "@/lib/api";
import type { EventSummary } from "@/lib/types";
import { fmt, plural, pluralWord } from "@/lib/utils";
import { Badge, Card, EmptyState, Input, Skeleton } from "@/components/ui";
import { EventCover } from "@/components/shared";

export function CatalogPage() {
  const [q, setQ] = useState("");
  const { data = [], isLoading } = useQuery({ queryKey: ["events"], queryFn: () => api<EventSummary[]>("/events") });
  const items = data.filter((e) => !q || `${e.title} ${e.description} ${e.location}`.toLowerCase().includes(q.toLowerCase()));
  const featured = data.find((e) => e.status === "PUBLISHED");

  return (
    <div>
      <section className="relative overflow-hidden border-b border-border">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgb(var(--brand)/0.15),transparent_60%)]" />
        <div className="relative mx-auto grid max-w-6xl gap-10 px-4 py-14 md:grid-cols-[1.2fr_1fr] md:py-20">
          <div>
            <Badge tone="brand"><Sparkles className="h-3 w-3" />Com assistente de IA que cita as fontes</Badge>
            <h1 className="mt-4 text-4xl font-extrabold leading-tight sm:text-5xl">Eventos acadêmicos sem fila de dúvidas no WhatsApp.</h1>
            <p className="mt-4 max-w-xl text-lg text-subtle">Inscreva-se nas sessões, receba seu ingresso digital e tire dúvidas com um assistente que responde pelo regulamento oficial. A comissão resolve imprevistos com um agente que investiga o impacto e propõe o plano.</p>
            <div className="mt-6 flex flex-wrap gap-3 text-sm text-subtle">
              <span className="flex items-center gap-1.5"><ShieldCheck className="h-4 w-4 text-ok" />Nenhuma ação sem sua confirmação</span>
              <span className="flex items-center gap-1.5"><Users className="h-4 w-4 text-brand" />Vagas garantidas sem overbooking</span>
            </div>
          </div>
          {featured && (
            <Link to={`/eventos/${featured.slug}`} className="group">
              <EventCover category={featured.category} title={featured.title} className="rounded-2xl p-6 shadow-xl transition group-hover:-translate-y-1">
                <p className="text-xs font-semibold uppercase tracking-wider text-white/80">Em destaque</p>
                <h2 className="mt-2 text-2xl font-bold">{featured.title}</h2>
                <p className="mt-2 text-sm text-white/85">{fmt.period(featured.start_at, featured.end_at)}</p>
                <div className="mt-8 flex items-end justify-between">
                  <div className="text-sm text-white/85"><p className="text-3xl font-bold text-white">{featured.sessions_count}</p>{pluralWord(featured.sessions_count, "sessão", "sessões")}</div>
                  <div className="text-sm text-white/85"><p className="text-3xl font-bold text-white">{featured.total_registered}</p>{pluralWord(featured.total_registered, "inscrição", "inscrições")}</div>
                  <span className="flex items-center gap-1 rounded-full bg-white/15 px-3 py-1.5 text-sm font-medium">Ver programação<ArrowRight className="h-4 w-4" /></span>
                </div>
              </EventCover>
            </Link>
          )}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-10">
        <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <h2 className="text-2xl font-bold">Próximos eventos</h2>
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-subtle" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar evento" className="pl-9" />
          </div>
        </div>
        {isLoading ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-72" />)}</div>
        ) : items.length === 0 ? (
          <EmptyState title="Nenhum evento encontrado" description="Tente outra busca." />
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((e) => (
              <Link key={e.id} to={`/eventos/${e.slug}`} className="group">
                <Card className="h-full overflow-hidden transition group-hover:-translate-y-0.5 group-hover:shadow-xl">
                  <EventCover category={e.category} title={e.title} className="h-32 p-4">
                    <Badge className="bg-white/20 text-white">{e.category === "HACKATHON" ? "Hackathon" : "Acadêmico"}</Badge>
                  </EventCover>
                  <div className="p-5">
                    <h3 className="text-lg font-semibold group-hover:text-brand">{e.title}</h3>
                    <p className="mt-1 line-clamp-2 text-sm text-subtle">{e.description}</p>
                    <div className="mt-4 space-y-1.5 text-sm text-subtle">
                      <p className="flex items-center gap-2"><CalendarDays className="h-4 w-4" />{fmt.period(e.start_at, e.end_at)}</p>
                      <p className="flex items-center gap-2"><MapPin className="h-4 w-4" /><span className="truncate">{e.location}</span></p>
                    </div>
                    <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-sm">
                      <span className="text-subtle">{plural(e.sessions_count, "sessão", "sessões")}</span>
                      <span className="font-medium text-brand">{plural(e.total_capacity - e.total_registered, "vaga aberta", "vagas abertas")}</span>
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
