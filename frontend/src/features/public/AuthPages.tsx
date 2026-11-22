import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { friendlyError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Card, Input, Label } from "@/components/ui";
import { Logo } from "@/components/layout/common";

const DEMO = [
  { email: "participante@exemplo.com", label: "Lucas", role: "Participante" },
  { email: "maria@exemplo.com", label: "Maria", role: "Participante" },
  { email: "ana.org@exemplo.com", label: "Ana", role: "Comissão (Semana FACOM)" },
  { email: "carla.staff@exemplo.com", label: "Carla", role: "Credenciamento" },
  { email: "bruno.org@exemplo.com", label: "Bruno", role: "Comissão (Hackathon)" },
  { email: "admin@exemplo.com", label: "Admin", role: "Administrador" },
];

function Shell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-[calc(100vh-12rem)] max-w-md flex-col justify-center px-4 py-12">
      <div className="mb-6 flex justify-center"><Logo /></div>
      <Card className="p-6 sm:p-8">
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-subtle">{subtitle}</p>
        <div className="mt-6">{children}</div>
      </Card>
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e?: React.FormEvent, override?: { email: string; password: string }) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(override?.email ?? email, override?.password ?? password);
      const next = params.get("next");
      nav(next ?? (u.role === "participant" ? "/" : u.role === "staff" ? "/painel/checkin" : "/painel"));
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Entrar" subtitle="Acesse suas inscrições, ingressos e o assistente do evento.">
      <form onSubmit={submit} className="space-y-4">
        <div><Label>E-mail</Label><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" /></div>
        <div><Label>Senha</Label><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" /></div>
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button type="submit" className="w-full" loading={busy}>Entrar</Button>
      </form>
      <p className="mt-4 text-center text-sm text-subtle">Ainda não tem conta? <Link to="/cadastro" className="font-medium text-brand">Cadastre-se</Link></p>
      <div className="mt-6 border-t border-border pt-5">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-subtle">Contas de demonstração (senha: senha123)</p>
        <div className="grid grid-cols-2 gap-2">
          {DEMO.map((d) => (
            <button key={d.email} disabled={busy} onClick={() => submit(undefined, { email: d.email, password: "senha123" })}
              className="rounded-xl border border-border p-2.5 text-left text-sm transition hover:border-brand/50 hover:bg-brand-soft/40">
              <p className="font-medium">{d.label}</p><p className="text-xs text-subtle">{d.role}</p>
            </button>
          ))}
        </div>
      </div>
    </Shell>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", course: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({ ...form, course: form.course || undefined });
      nav("/");
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Criar conta" subtitle="Gratuita e aberta ao público externo.">
      <form onSubmit={submit} className="space-y-4">
        <div><Label>Nome completo</Label><Input value={form.name} onChange={set("name")} required minLength={2} /></div>
        <div><Label>E-mail</Label><Input type="email" value={form.email} onChange={set("email")} required /></div>
        <div><Label>Senha</Label><Input type="password" value={form.password} onChange={set("password")} required minLength={6} /></div>
        <div><Label hint="(opcional)">Curso</Label><Input value={form.course} onChange={set("course")} /></div>
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button type="submit" className="w-full" loading={busy}>Criar conta</Button>
      </form>
      <p className="mt-4 text-center text-sm text-subtle">Já tem conta? <Link to="/entrar" className="font-medium text-brand">Entrar</Link></p>
    </Shell>
  );
}
