import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, LayoutDashboard, LogOut, Moon, Sun, Ticket, User as UserIcon } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Notification } from "@/lib/types";
import { cn, fmt, initials } from "@/lib/utils";
import { Button } from "@/components/ui";
import { Markdown } from "@/components/shared";

export function Logo({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 font-display text-lg font-extrabold tracking-tight">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-brand-fg">
        <svg viewBox="0 0 32 32" className="h-5 w-5"><path d="M9 22l7-12 7 12" stroke="currentColor" strokeWidth="3.2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </span>
      <span>academic<span className="text-brand">-events</span></span>
    </Link>
  );
}

export function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch { /* ignore */ }
  }, [dark]);
  return (
    <Button variant="ghost" size="icon" onClick={() => setDark((d) => !d)} aria-label="Alternar tema">
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

function useClickOutside(ref: React.RefObject<HTMLElement>, onOut: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && onOut();
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, onOut]);
}

export function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false));
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["notifications"], queryFn: () => api<Notification[]>("/me/notifications"), refetchInterval: 20_000 });
  const unread = data.filter((n) => !n.read_at).length;
  const markRead = useMutation({ mutationFn: () => api("/me/notifications/read", { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }) });
  return (
    <div className="relative" ref={ref}>
      <Button variant="ghost" size="icon" aria-label="Notificações" onClick={() => { setOpen((o) => !o); if (!open && unread) markRead.mutate(); }}>
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">{unread}</span>}
      </Button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-[min(92vw,380px)] animate-fade-in overflow-hidden rounded-2xl border border-border bg-surface shadow-xl">
          <div className="border-b border-border px-4 py-3 text-sm font-semibold">Notificações</div>
          <div className="max-h-96 overflow-y-auto scrollbar-thin">
            {data.length === 0 && <p className="p-6 text-center text-sm text-subtle">Nenhuma notificação por enquanto.</p>}
            {data.map((n) => (
              <div key={n.id} className={cn("border-b border-border/60 px-4 py-3 last:border-0", !n.read_at && "bg-brand-soft/40")}>
                <p className="text-sm font-medium">{n.title}</p>
                <div className="mt-1 text-sm text-subtle"><Markdown text={n.body} compact /></div>
                <p className="mt-1 text-xs text-subtle">{fmt.relative(n.created_at)}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function UserMenu() {
  const { user, logout, isManager } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  useClickOutside(ref, () => setOpen(false));
  if (!user) return null;
  const roleLabel = { participant: "Participante", staff: "Credenciamento", organizer: "Comissão organizadora", admin: "Administrador" }[user.role];
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 rounded-full p-0.5 pr-2 hover:bg-muted" aria-label="Menu do usuário">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-soft text-xs font-bold text-brand">{initials(user.name)}</span>
        <span className="hidden text-sm font-medium md:block">{user.name.split(" ")[0]}</span>
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-60 animate-fade-in overflow-hidden rounded-2xl border border-border bg-surface p-1.5 shadow-xl">
          <div className="px-3 py-2">
            <p className="text-sm font-semibold">{user.name}</p>
            <p className="text-xs text-subtle">{roleLabel}</p>
          </div>
          <div className="my-1 h-px bg-border" />
          <MenuItem icon={<Ticket className="h-4 w-4" />} onClick={() => { setOpen(false); nav("/meus-ingressos"); }}>Meus ingressos</MenuItem>
          {isManager && <MenuItem icon={<LayoutDashboard className="h-4 w-4" />} onClick={() => { setOpen(false); nav(user.role === "staff" ? "/painel/checkin" : "/painel"); }}>Painel da organização</MenuItem>}
          <MenuItem icon={<LogOut className="h-4 w-4" />} onClick={() => { logout(); nav("/"); }}>Sair</MenuItem>
        </div>
      )}
    </div>
  );
}

function MenuItem({ icon, children, onClick }: { icon: React.ReactNode; children: React.ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm hover:bg-muted">
      <span className="text-subtle">{icon}</span>{children}
    </button>
  );
}

export function LoginButton() {
  return <Link to="/entrar"><Button size="sm"><UserIcon className="h-4 w-4" />Entrar</Button></Link>;
}
