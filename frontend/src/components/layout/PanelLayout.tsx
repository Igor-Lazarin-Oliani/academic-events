import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, Bot, CheckSquare, ClipboardCheck, ClipboardList, FlaskConical, GitBranch, Inbox, LayoutDashboard, Menu, MessageSquareWarning, Route, Siren, Users, X } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EventSummary, Page, Proposal } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Select, Spinner } from "@/components/ui";
import { Logo, NotificationsBell, ThemeToggle, UserMenu } from "./common";

interface PanelCtx { event: EventSummary | null; events: EventSummary[]; setEventId: (id: string) => void }
const Ctx = createContext<PanelCtx>({ event: null, events: [], setEventId: () => {} });
export const usePanelEvent = () => useContext(Ctx);

const NAV = [
  { group: "Operação", items: [
    { to: "/painel", label: "Visão geral", icon: LayoutDashboard, end: true, roles: ["organizer", "admin"] },
    { to: "/painel/ocorrencias", label: "Ocorrências", icon: Siren, roles: ["organizer", "admin"] },
    { to: "/painel/aprovacoes", label: "Aprovações", icon: CheckSquare, roles: ["organizer", "admin"], badge: "approvals" },
    { to: "/painel/inscritos", label: "Inscritos", icon: Users, roles: ["organizer", "admin", "staff"] },
    { to: "/painel/checkin", label: "Check-in", icon: ClipboardCheck, roles: ["organizer", "admin", "staff"] },
    { to: "/painel/chamados", label: "Chamados", icon: Inbox, roles: ["organizer", "admin"] },
  ]},
  { group: "Conhecimento", items: [
    { to: "/painel/grafo", label: "Grafo do evento", icon: GitBranch, roles: ["organizer", "admin"] },
    { to: "/painel/conhecimento", label: "Base de conhecimento", icon: ClipboardList, roles: ["organizer", "admin"] },
  ]},
  { group: "Agentes e qualidade", items: [
    { to: "/painel/trajetorias", label: "Trajetórias", icon: Route, roles: ["organizer", "admin"] },
    { to: "/painel/evals", label: "Evals", icon: FlaskConical, roles: ["organizer", "admin"] },
    { to: "/painel/agentes", label: "Arquitetura", icon: Bot, roles: ["organizer", "admin"] },
    { to: "/painel/auditoria", label: "Auditoria (Logs)", icon: Activity, roles: ["organizer", "admin"] },
  ]},
];

export function PanelLayout() {
  const { user, loading } = useAuth();
  const [mobile, setMobile] = useState(false);
  const loc = useLocation();
  useEffect(() => setMobile(false), [loc.pathname]);
  const { data: all = [], isLoading } = useQuery({ queryKey: ["events"], queryFn: () => api<EventSummary[]>("/events"), enabled: !!user });
  const events = useMemo(() => {
    if (!user) return [];
    if (user.role === "admin" || user.managed_event_ids == null) return all;
    return all.filter((e) => user.managed_event_ids!.includes(e.id));
  }, [all, user]);
  const [eventId, setEventIdState] = useState<string | null>(() => { try { return localStorage.getItem("ae.panelEvent"); } catch { return null; } });
  const event = events.find((e) => e.id === eventId) ?? events[0] ?? null;
  const setEventId = (id: string) => { setEventIdState(id); try { localStorage.setItem("ae.panelEvent", id); } catch { /* ignore */ } };
  const { data: pendingTotal = 0 } = useQuery({
    queryKey: ["proposals", "pending", event?.id], enabled: !!event && user?.role !== "staff", refetchInterval: 15_000,
    queryFn: () => api<Page<Proposal>>(`/proposals?status=PENDING&kind=ACTION_PLAN&event_id=${event!.id}`), select: (p) => p.total,
  });

  if (loading) return <div className="grid h-full place-items-center"><Spinner /></div>;
  if (!user) return <Navigate to="/entrar?next=/painel" replace />;
  if (!["organizer", "admin", "staff"].includes(user.role)) return <Navigate to="/" replace />;
  if (user.role === "staff" && (loc.pathname === "/painel" || loc.pathname === "/painel/")) return <Navigate to="/painel/checkin" replace />;

  const sidebar = (
    <aside className="flex h-full w-64 flex-col border-r border-border bg-surface">
      <div className="flex h-16 items-center px-5"><Logo to="/painel" /></div>
      <div className="px-4 pb-3">
        <p className="mb-1 text-xs font-medium text-subtle">Evento</p>
        <Select value={event?.id ?? ""} onChange={(e) => setEventId(e.target.value)} aria-label="Evento">
          {events.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
        </Select>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 pb-4 scrollbar-thin">
        {NAV.map((g) => {
          const items = g.items.filter((i) => i.roles.includes(user.role));
          if (!items.length) return null;
          return (
            <div key={g.group} className="mt-3">
              <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">{g.group}</p>
              {items.map((i) => (
                <NavLink key={i.to} to={i.to} end={(i as any).end}
                  className={({ isActive }) => cn("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition", isActive ? "bg-brand-soft text-brand" : "text-subtle hover:bg-muted hover:text-fg")}>
                  <i.icon className="h-4 w-4" />
                  {i.label}
                  {(i as any).badge === "approvals" && pendingTotal > 0 && <span className="ml-auto rounded-full bg-accent px-1.5 text-xs font-bold text-black">{pendingTotal}</span>}
                </NavLink>
              ))}
            </div>
          );
        })}
      </nav>
      <div className="border-t border-border p-3">
        <NavLink to="/" className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-subtle hover:bg-muted"><MessageSquareWarning className="h-4 w-4" />Ver portal do participante</NavLink>
      </div>
    </aside>
  );

  return (
    <Ctx.Provider value={{ event, events, setEventId }}>
      <div className="flex h-full">
        <div className="hidden lg:block">{sidebar}</div>
        {mobile && (
          <div className="fixed inset-0 z-40 flex lg:hidden">
            <div className="h-full animate-fade-in">{sidebar}</div>
            <div className="flex-1 bg-black/40" onClick={() => setMobile(false)} />
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 flex h-16 items-center gap-2 border-b border-border bg-bg/80 px-4 backdrop-blur lg:px-8">
            <button className="rounded-lg p-2 hover:bg-muted lg:hidden" onClick={() => setMobile((m) => !m)} aria-label="Menu">{mobile ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}</button>
            <p className="truncate text-sm text-subtle">{event?.title}</p>
            <div className="ml-auto flex items-center gap-1"><ThemeToggle /><NotificationsBell /><UserMenu /></div>
          </header>
          <main className="flex-1 overflow-y-auto px-4 py-6 lg:px-8 scrollbar-thin">
            {isLoading ? <Spinner /> : event ? <Outlet /> : <p className="text-subtle">Você não gerencia nenhum evento.</p>}
          </main>
        </div>
      </div>
    </Ctx.Provider>
  );
}
