import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { api, friendlyError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EventSummary } from "@/lib/types";
import { KIND_LABEL } from "@/lib/utils";
import { Button, Card, CardBody, CardHeader, Input, Label, PageHeader, Select, Textarea, useToast } from "@/components/ui";
import { usePanelEvent } from "@/components/layout/PanelLayout";

const CATEGORIES = { ACADEMIC: "Acadêmico", HACKATHON: "Hackathon" };
const MODALITIES = { IN_PERSON: "Presencial", ONLINE: "On-line", HYBRID: "Híbrido" };

interface SessionDraft { key: number; code: string; title: string; kind: string; track: string; start_at: string; end_at: string; max_capacity: string; workload_hours: string }

let nextKey = 1;
const emptySession = (): SessionDraft => ({ key: nextKey++, code: "", title: "", kind: "PALESTRA", track: "Geral", start_at: "", end_at: "", max_capacity: "50", workload_hours: "2" });

/** Valor de <input type="datetime-local"> (horário local do navegador) para ISO com fuso. */
const toIso = (local: string) => new Date(local).toISOString();

const slugify = (s: string) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);

export function NewEventPage() {
  const { user } = useAuth();
  const { setEventId } = usePanelEvent();
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();

  const [form, setForm] = useState({
    title: "", slug: "", description: "", category: "ACADEMIC", modality: "IN_PERSON", location: "",
    start_at: "", end_at: "", max_minicursos_per_participant: "3",
  });
  const [slugTouched, setSlugTouched] = useState(false);
  const [sessions, setSessions] = useState<SessionDraft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user?.role !== "admin") return <Navigate to="/painel" replace />;

  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v, ...(k === "title" && !slugTouched ? { slug: slugify(v) } : {}) }));
  const setSession = (key: number, k: keyof SessionDraft, v: string) => setSessions((xs) => xs.map((s) => (s.key === key ? { ...s, [k]: v } : s)));

  function validate(): string | null {
    if (!/^[a-z0-9-]{3,80}$/.test(form.slug)) return "O identificador (slug) deve ter de 3 a 80 caracteres: letras minúsculas, números e hífen.";
    if (new Date(form.end_at) <= new Date(form.start_at)) return "O término do evento deve ser depois do início.";
    const codes = new Set<string>();
    for (const [i, s] of sessions.entries()) {
      const n = `Atividade ${i + 1}`;
      if (!s.code.trim() || s.title.trim().length < 3) return `${n}: informe o código e um título com pelo menos 3 caracteres.`;
      const code = s.code.trim().toUpperCase();
      if (codes.has(code)) return `${n}: o código ${code} já foi usado em outra atividade.`;
      codes.add(code);
      if (!s.start_at || !s.end_at || new Date(s.end_at) <= new Date(s.start_at)) return `${n}: o término deve ser depois do início.`;
      if (new Date(s.start_at) < new Date(form.start_at) || new Date(s.end_at) > new Date(form.end_at)) return `${n}: precisa acontecer dentro do período do evento.`;
      if (!(Number(s.max_capacity) > 0)) return `${n}: a capacidade deve ser maior que zero.`;
    }
    return null;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const problem = validate();
    setError(problem);
    if (problem) return;
    setBusy(true);
    try {
      const created = await api<EventSummary>("/events", {
        body: {
          ...form,
          start_at: toIso(form.start_at),
          end_at: toIso(form.end_at),
          max_minicursos_per_participant: Number(form.max_minicursos_per_participant),
          sessions: sessions.map(({ key, ...s }) => ({
            ...s, code: s.code.trim().toUpperCase(), start_at: toIso(s.start_at), end_at: toIso(s.end_at),
            max_capacity: Number(s.max_capacity), workload_hours: Number(s.workload_hours),
          })),
        },
      });
      await qc.invalidateQueries({ queryKey: ["events"] });
      setEventId(created.id);
      toast({ kind: "success", title: "Evento criado", description: `${created.title} já aparece no catálogo.` });
      nav("/painel");
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-4xl">
      <PageHeader eyebrow="Administração" title="Novo evento" description="Cadastre o evento e, se quiser, a programação inicial. Tudo é salvo de uma vez: se algo estiver errado, nada é criado." />

      <Card className="mb-6">
        <CardHeader title="Dados do evento" />
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2"><Label>Título</Label><Input value={form.title} onChange={(e) => set("title", e.target.value)} required minLength={3} maxLength={200} /></div>
          <div className="sm:col-span-2">
            <Label hint="Usado no endereço: /eventos/…">Identificador (slug)</Label>
            <Input value={form.slug} onChange={(e) => { setSlugTouched(true); set("slug", e.target.value.toLowerCase()); }} required pattern="[a-z0-9\-]{3,80}" />
          </div>
          <div className="sm:col-span-2"><Label>Descrição</Label><Textarea value={form.description} onChange={(e) => set("description", e.target.value)} /></div>
          <div><Label>Categoria</Label><Select value={form.category} onChange={(e) => set("category", e.target.value)}>{Object.entries(CATEGORIES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></div>
          <div><Label>Modalidade</Label><Select value={form.modality} onChange={(e) => set("modality", e.target.value)}>{Object.entries(MODALITIES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></div>
          <div className="sm:col-span-2"><Label>Local</Label><Input value={form.location} onChange={(e) => set("location", e.target.value)} required /></div>
          <div><Label>Início</Label><Input type="datetime-local" value={form.start_at} onChange={(e) => set("start_at", e.target.value)} required /></div>
          <div><Label>Término</Label><Input type="datetime-local" value={form.end_at} onChange={(e) => set("end_at", e.target.value)} required /></div>
          <div><Label hint="Por participante">Limite de minicursos</Label><Input type="number" min={1} max={20} value={form.max_minicursos_per_participant} onChange={(e) => set("max_minicursos_per_participant", e.target.value)} required /></div>
        </CardBody>
      </Card>

      <Card className="mb-6">
        <CardHeader title="Programação" description="Opcional. Dá para adicionar atividades depois."
          action={<Button type="button" variant="secondary" size="sm" onClick={() => setSessions((xs) => [...xs, emptySession()])}><Plus className="h-4 w-4" />Adicionar atividade</Button>} />
        <CardBody className="space-y-4">
          {sessions.length === 0 && <p className="text-sm text-subtle">Nenhuma atividade adicionada.</p>}
          {sessions.map((s, i) => (
            <div key={s.key} className="rounded-xl border border-border p-4">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-semibold">Atividade {i + 1}</p>
                <Button type="button" variant="ghost" size="sm" onClick={() => setSessions((xs) => xs.filter((x) => x.key !== s.key))} aria-label={`Remover atividade ${i + 1}`}><Trash2 className="h-4 w-4" /></Button>
              </div>
              <div className="grid gap-3 sm:grid-cols-4">
                <div><Label>Código</Label><Input value={s.code} onChange={(e) => setSession(s.key, "code", e.target.value)} maxLength={20} placeholder="P01" /></div>
                <div className="sm:col-span-3"><Label>Título</Label><Input value={s.title} onChange={(e) => setSession(s.key, "title", e.target.value)} maxLength={200} /></div>
                <div><Label>Tipo</Label><Select value={s.kind} onChange={(e) => setSession(s.key, "kind", e.target.value)}>{Object.entries(KIND_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></div>
                <div><Label>Trilha</Label><Input value={s.track} onChange={(e) => setSession(s.key, "track", e.target.value)} /></div>
                <div><Label>Vagas</Label><Input type="number" min={1} value={s.max_capacity} onChange={(e) => setSession(s.key, "max_capacity", e.target.value)} /></div>
                <div><Label>Carga horária (h)</Label><Input type="number" min={0} max={40} value={s.workload_hours} onChange={(e) => setSession(s.key, "workload_hours", e.target.value)} /></div>
                <div className="sm:col-span-2"><Label>Início</Label><Input type="datetime-local" value={s.start_at} onChange={(e) => setSession(s.key, "start_at", e.target.value)} /></div>
                <div className="sm:col-span-2"><Label>Término</Label><Input type="datetime-local" value={s.end_at} onChange={(e) => setSession(s.key, "end_at", e.target.value)} /></div>
              </div>
            </div>
          ))}
        </CardBody>
      </Card>

      {error && <p className="mb-4 rounded-xl border border-danger/40 bg-danger/10 p-3 text-sm text-danger" role="alert">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={() => nav("/painel")}>Cancelar</Button>
        <Button type="submit" loading={busy}>Criar evento</Button>
      </div>
    </form>
  );
}
