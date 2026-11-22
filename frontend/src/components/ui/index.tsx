import { createContext, forwardRef, useCallback, useContext, useEffect, useState, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { CheckCircle2, ChevronLeft, ChevronRight, Loader2, X, XCircle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

/* ---------------- Button ---------------- */
type Variant = "primary" | "secondary" | "ghost" | "outline" | "danger" | "success";
type Size = "sm" | "md" | "lg" | "icon";
const variants: Record<Variant, string> = {
  primary: "bg-brand text-brand-fg hover:bg-brand/90 shadow-sm",
  secondary: "bg-muted text-fg hover:bg-border/70",
  ghost: "hover:bg-muted text-fg",
  outline: "border border-border bg-surface hover:bg-muted text-fg",
  danger: "bg-danger text-white hover:bg-danger/90",
  success: "bg-ok text-white hover:bg-ok/90",
};
const sizes: Record<Size, string> = { sm: "h-8 px-3 text-sm gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-12 px-6 text-base gap-2", icon: "h-9 w-9" };

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> { variant?: Variant; size?: Size; loading?: boolean }
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => (
  <button ref={ref} disabled={disabled || loading}
    className={cn("inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap", variants[variant], sizes[size], className)} {...props}>
    {loading && <Loader2 className="h-4 w-4 animate-spin" />}
    {children}
  </button>
));
Button.displayName = "Button";

/* ---------------- Card ---------------- */
export function Card({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-2xl border border-border bg-surface shadow-card", className)} {...p} />;
}
export function CardHeader({ title, description, action, className }: { title: ReactNode; description?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 p-5 pb-3", className)}>
      <div>
        <h3 className="text-base font-semibold">{title}</h3>
        {description && <p className="mt-0.5 text-sm text-subtle">{description}</p>}
      </div>
      {action}
    </div>
  );
}
export const CardBody = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(({ className, ...p }, ref) => (
  <div ref={ref} className={cn("p-5 pt-2", className)} {...p} />
));
CardBody.displayName = "CardBody";

/* ---------------- Badge ---------------- */
type Tone = "brand" | "ok" | "warn" | "danger" | "muted" | "accent";
const tones: Record<Tone, string> = {
  brand: "bg-brand-soft text-brand",
  ok: "bg-ok/10 text-ok",
  warn: "bg-warn/10 text-warn",
  danger: "bg-danger/10 text-danger",
  muted: "bg-muted text-subtle",
  accent: "bg-accent/15 text-accent",
};
export function Badge({ tone = "muted", className, children }: { tone?: Tone; className?: string; children: ReactNode }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium", tones[tone], className)}>{children}</span>;
}

/* ---------------- Inputs ---------------- */
const field = "w-full rounded-lg border border-border bg-surface px-3 text-sm placeholder:text-subtle/70 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 transition";
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => <input ref={ref} className={cn(field, "h-10", className)} {...p} />);
Input.displayName = "Input";
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => <textarea ref={ref} className={cn(field, "py-2.5 min-h-[90px]", className)} {...p} />);
Textarea.displayName = "Textarea";
export function Select({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(field, "h-10 pr-8", className)} {...p} />;
}
export function Label({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return <label className="mb-1.5 block text-sm font-medium">{children}{hint && <span className="ml-1 font-normal text-subtle">{hint}</span>}</label>;
}

/* ---------------- Feedback ---------------- */
export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-5 w-5 animate-spin text-subtle", className)} />;
}
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-muted", className)} />;
}
export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border px-6 py-12 text-center">
      {icon && <div className="mb-1 text-subtle">{icon}</div>}
      <p className="font-semibold">{title}</p>
      {description && <p className="max-w-md text-sm text-subtle">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="rounded-xl border border-danger/30 bg-danger/5 p-4 text-sm text-danger">{msg}</div>;
}

export function Stat({ label, value, hint, icon, tone = "brand" }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: Tone }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-subtle">{label}</p>
        {icon && <span className={cn("rounded-lg p-2", tones[tone])}>{icon}</span>}
      </div>
      <p className="mt-2 text-3xl font-bold font-display tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-subtle">{hint}</p>}
    </Card>
  );
}

export function Progress({ value, tone = "brand", className }: { value: number; tone?: "brand" | "ok" | "warn" | "danger"; className?: string }) {
  const color = { brand: "bg-brand", ok: "bg-ok", warn: "bg-warn", danger: "bg-danger" }[tone];
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}>
      <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }} />
    </div>
  );
}

/* ---------------- Tabs ---------------- */
export function Tabs<T extends string>({ value, onChange, items, className }: { value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode; count?: number }[]; className?: string }) {
  return (
    <div className={cn("inline-flex max-w-full overflow-x-auto rounded-xl bg-muted p-1 scrollbar-thin", className)} role="tablist">
      {items.map((it) => (
        <button key={it.value} role="tab" aria-selected={value === it.value} onClick={() => onChange(it.value)}
          className={cn("whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm font-medium transition", value === it.value ? "bg-surface shadow-sm text-fg" : "text-subtle hover:text-fg")}>
          {it.label}
          {it.count !== undefined && <span className="ml-1.5 rounded-full bg-border/70 px-1.5 text-xs">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------------- Pagination ---------------- */
export function Pagination({ page, pageSize, total, onPageChange, loading, className }: { page: number; pageSize: number; total: number; onPageChange: (p: number) => void; loading?: boolean; className?: string }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  // Se a página atual deixou de existir (ex.: itens resolvidos/arquivados), volta para a última válida.
  useEffect(() => { if (!loading && page > 0 && page >= pages) onPageChange(pages - 1); }, [loading, page, pages, onPageChange]);
  if (total === 0) return null;
  const first = page * pageSize + 1;
  const last = Math.min(total, (page + 1) * pageSize);
  return (
    <div className={cn("mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4", className)}>
      <span className="text-xs text-subtle">Mostrando {first.toLocaleString("pt-BR")}–{last.toLocaleString("pt-BR")} de {total.toLocaleString("pt-BR")}</span>
      {pages > 1 && (
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={page === 0 || loading} onClick={() => onPageChange(page - 1)}><ChevronLeft className="h-4 w-4" />Anterior</Button>
          <span className="text-xs tabular-nums text-subtle">Página {page + 1} de {pages}</span>
          <Button size="sm" variant="outline" disabled={page >= pages - 1 || loading} onClick={() => onPageChange(page + 1)}>Próxima<ChevronRight className="h-4 w-4" /></Button>
        </div>
      )}
    </div>
  );
}

/* ---------------- Dialog ---------------- */
export function Dialog({ open, onClose, title, description, children, footer, wide }: { open: boolean; onClose: () => void; title: ReactNode; description?: ReactNode; children?: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 backdrop-blur-sm sm:items-center sm:p-4" onClick={onClose}>
      <div className={cn("w-full animate-fade-in rounded-t-2xl border border-border bg-surface shadow-xl sm:rounded-2xl", wide ? "sm:max-w-2xl" : "sm:max-w-md")} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal>
        <div className="flex items-start justify-between gap-4 border-b border-border p-5">
          <div>
            <h3 className="text-lg font-semibold">{title}</h3>
            {description && <p className="mt-1 text-sm text-subtle">{description}</p>}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Fechar"><X className="h-4 w-4" /></Button>
        </div>
        {children && <div className="max-h-[70vh] overflow-y-auto p-5 scrollbar-thin">{children}</div>}
        {footer && <div className="flex justify-end gap-2 border-t border-border p-4">{footer}</div>}
      </div>
    </div>
  );
}

/* ---------------- Toast ---------------- */
interface ToastItem { id: number; kind: "success" | "error" | "info"; title: string; description?: string }
const ToastCtx = createContext<(t: Omit<ToastItem, "id">) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((t: Omit<ToastItem, "id">) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { ...t, id }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 left-1/2 z-[60] flex w-full max-w-sm -translate-x-1/2 flex-col gap-2 px-4 sm:left-auto sm:right-4 sm:translate-x-0">
        {items.map((t) => (
          <div key={t.id} className="pointer-events-auto flex animate-fade-in gap-3 rounded-xl border border-border bg-surface p-4 shadow-xl">
            {t.kind === "success" ? <CheckCircle2 className="h-5 w-5 shrink-0 text-ok" /> : t.kind === "error" ? <XCircle className="h-5 w-5 shrink-0 text-danger" /> : <Info className="h-5 w-5 shrink-0 text-brand" />}
            <div className="text-sm">
              <p className="font-medium">{t.title}</p>
              {t.description && <p className="mt-0.5 text-subtle">{t.description}</p>}
            </div>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

export function PageHeader({ title, description, actions, eyebrow }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-brand">{eyebrow}</p>}
        <h1 className="text-2xl font-bold sm:text-3xl">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-subtle">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
