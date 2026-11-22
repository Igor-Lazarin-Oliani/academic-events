import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, GitBranch, ShieldAlert, Upload } from "lucide-react";
import { api, friendlyError } from "@/lib/api";
import type { KnowledgeDoc } from "@/lib/types";
import { cn, fmt, plural, pluralWord } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, Dialog, Input, Label, PageHeader, Select, Skeleton, Textarea, useToast } from "@/components/ui";
import { Markdown } from "@/components/shared";
import { usePanelEvent } from "@/components/layout/PanelLayout";

/* ---------------- Grafo ---------------- */
interface GNode { id: string; type: string; label: string; attrs: any }
const COL: Record<string, number> = { room: 0, session: 1, speaker: 2 };
const W = 720, ROW = 30, PAD = 30, COLX = [80, 360, 640], NW = 150;

export function GraphPage() {
  const { event } = usePanelEvent();
  const { data, isLoading } = useQuery({ queryKey: ["graph", event!.id], queryFn: () => api<{ nodes: GNode[]; edges: { source: string; target: string; relation: string }[] }>(`/events/${event!.id}/graph`) });
  const [sel, setSel] = useState<GNode | null>(null);
  const layout = useMemo(() => {
    if (!data) return null;
    const cols: GNode[][] = [[], [], []];
    data.nodes.filter((n) => n.type in COL).forEach((n) => cols[COL[n.type]].push(n));
    cols[1].sort((a, b) => a.attrs.start_at.localeCompare(b.attrs.start_at));
    const height = Math.max(...cols.map((c) => c.length)) * ROW + PAD * 2;
    const pos: Record<string, { x: number; y: number }> = {};
    cols.forEach((c, ci) => { const off = (height - c.length * ROW) / 2; c.forEach((n, i) => { pos[n.id] = { x: COLX[ci], y: off + i * ROW + ROW / 2 }; }); });
    const edges = data.edges.filter((e) => pos[e.source] && pos[e.target]);
    return { cols, pos, edges, height };
  }, [data]);
  const neighbors = useMemo(() => {
    if (!sel || !layout) return new Set<string>();
    const s = new Set([sel.id]);
    layout.edges.forEach((e) => { if (e.source === sel.id) s.add(e.target); if (e.target === sel.id) s.add(e.source); });
    if (sel.type !== "session") layout.edges.forEach((e) => { if (s.has(e.source) && e.source.startsWith("session:")) s.add(e.target); });
    return s;
  }, [sel, layout]);
  const key = sel ? (sel.type === "session" ? sel.attrs.code : sel.label) : "";
  const { data: impact } = useQuery({ queryKey: ["impact", event!.id, sel?.id], enabled: !!sel, queryFn: () => api<any>(`/events/${event!.id}/graph/impact?node_type=${sel!.type}&key=${encodeURIComponent(key)}`) });

  return (
    <div>
      <PageHeader eyebrow="Grafo de conhecimento" title="Grafo do evento" description="Salas, sessões e palestrantes ligados por HELD_IN e PRESENTED_BY. É o mesmo grafo que o Agente de Operações consulta (query_impact_graph) para descobrir quem é afetado por uma mudança. Clique em um nó." />
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <Card className="overflow-x-auto p-4">
          {isLoading || !layout ? <Skeleton className="h-[500px]" /> : (
            <svg viewBox={`0 0 ${W} ${layout.height}`} className="w-full min-w-[640px]">
              {["Salas", "Sessões", "Palestrantes"].map((t, i) => <text key={t} x={COLX[i]} y={16} textAnchor="middle" className="fill-subtle text-[11px] font-semibold uppercase">{t}</text>)}
              {layout.edges.map((e, i) => {
                const a = layout.pos[e.source], b = layout.pos[e.target];
                const on = sel && neighbors.has(e.source) && neighbors.has(e.target);
                const [l, r] = a.x < b.x ? [a, b] : [b, a];
                return <path key={i} d={`M${l.x + NW / 2},${l.y} C${(l.x + r.x) / 2},${l.y} ${(l.x + r.x) / 2},${r.y} ${r.x - NW / 2},${r.y}`} fill="none"
                  stroke={on ? "rgb(var(--brand))" : "rgb(var(--border))"} strokeWidth={on ? 2 : 1} opacity={sel && !on ? 0.25 : 1} />;
              })}
              {layout.cols.flat().map((n) => {
                const p = layout.pos[n.id];
                const dim = sel && !neighbors.has(n.id);
                const isSel = sel?.id === n.id;
                const cancelled = n.attrs.status === "CANCELLED";
                const unavailable = n.type === "room" && n.attrs.available === false;
                return (
                  <g key={n.id} transform={`translate(${p.x - NW / 2},${p.y - 12})`} onClick={() => setSel(isSel ? null : n)} className="cursor-pointer" opacity={dim ? 0.3 : 1}>
                    <rect width={NW} height={24} rx={7} className={cn(isSel ? "fill-brand" : n.type === "session" ? "fill-brand-soft" : n.type === "room" ? "fill-muted" : "fill-accent/15", unavailable && "fill-danger/15")} stroke={isSel ? "none" : "rgb(var(--border))"} />
                    <text x={NW / 2} y={16} textAnchor="middle" className={cn("text-[11px] font-medium", isSel ? "fill-brand-fg" : "fill-fg", cancelled && "line-through")}>
                      {(n.type === "session" ? `${n.attrs.code} · ${n.attrs.registrations} insc.` : n.label).slice(0, 24)}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}
        </Card>
        <Card className="self-start">
          <CardHeader title={sel ? sel.label : "Análise de impacto"} description={sel ? `${sel.type}` : "Selecione uma sala, sessão ou palestrante"} />
          <CardBody>
            {!sel ? <p className="text-sm text-subtle"><GitBranch className="mb-2 h-6 w-6" />O caminho no grafo é a evidência: “Sala 105 -HELD_IN- S10” explica por que a S10 é afetada.</p> : !impact ? <Skeleton className="h-40" /> : (
              <div className="space-y-3">
                <div className="rounded-xl bg-brand-soft p-3 text-center"><p className="text-2xl font-bold text-brand">{impact.affected_participants}</p><p className="text-xs text-subtle">{pluralWord(impact.affected_participants, "participante distinto afetado", "participantes distintos afetados")}</p></div>
                {impact.affected_sessions.map((s: any) => (
                  <div key={s.session_code} className="rounded-xl border border-border p-3">
                    <p className="text-sm font-medium">{s.session_code} · {s.title}</p>
                    <p className="text-xs text-subtle">{fmt.weekdayShort(s.start_at)} {fmt.range(s.start_at, s.end_at)} · {plural(s.registrations, "inscrito", "inscritos")}</p>
                    <p className="mt-1 font-mono text-[10px] text-subtle">{s.path}</p>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

/* ---------------- Base de conhecimento ---------------- */
export function KnowledgePage() {
  const { event } = usePanelEvent();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: docs = [] } = useQuery({ queryKey: ["docs", event!.id, "all"], queryFn: () => api<KnowledgeDoc[]>(`/events/${event!.id}/knowledge?include_superseded=true`) });
  const [sel, setSel] = useState<string | null>(null);
  const current = sel ?? docs.find((d) => d.status === "ACTIVE")?.id ?? null;
  const { data: doc } = useQuery({ queryKey: ["doc", current], enabled: !!current, queryFn: () => api<any>(`/events/${event!.id}/knowledge/${current}`) });
  const [q, setQ] = useState("");
  const { data: hits, refetch, isFetching } = useQuery({ queryKey: ["ksearch", event!.id, q], enabled: false, queryFn: () => api<any[]>(`/events/${event!.id}/knowledge/search?q=${encodeURIComponent(q)}`) });
  const [upload, setUpload] = useState(false);
  const [form, setForm] = useState({ source_id: "", title: "", content: "", trust: "OFFICIAL" });
  const up = useMutation({
    mutationFn: () => api(`/events/${event!.id}/knowledge`, { body: form }),
    onSuccess: () => { toast({ kind: "success", title: "Documento indexado", description: "Versões anteriores do mesmo ID foram substituídas." }); setUpload(false); qc.invalidateQueries({ queryKey: ["docs"] }); },
    onError: (e) => toast({ kind: "error", title: "Falha ao indexar", description: friendlyError(e) }),
  });
  return (
    <div>
      <PageHeader eyebrow="Contexto governado" title="Base de conhecimento" description="Documentos versionados que o assistente pode citar. Cada resposta carrega fonte, seção, versão e confiabilidade. Documentos não verificados não viram regra, e instruções embutidas neles são removidas pelo guardrail."
        actions={<Button onClick={() => setUpload(true)}><Upload className="h-4 w-4" />Publicar documento</Button>} />
      <Card className="mb-6 p-4">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim()) refetch(); }}>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Teste a recuperação: ex. “posso trocar de minicurso?”" />
          <Button type="submit" variant="outline" loading={isFetching}>Buscar</Button>
        </form>
        {hits && (
          <div className="mt-3 space-y-2">
            {hits.length === 0 && <p className="text-sm text-subtle">Nenhum trecho recuperado: o assistente responderia “não encontrei”.</p>}
            {hits.map((h) => <div key={h.chunk_id} className="rounded-xl border border-border p-3 text-sm"><div className="flex items-center gap-2"><Badge tone={h.evidence.trust === "OFFICIAL" ? "brand" : "warn"}>{h.evidence.source_id} §{h.section}</Badge><span className="font-medium">{h.heading}</span><span className="ml-auto font-mono text-xs text-subtle">score {h.score}</span></div><p className="mt-1 line-clamp-2 text-subtle">{h.content}</p></div>)}
          </div>
        )}
      </Card>
      <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
        <div className="space-y-2">
          {docs.map((d) => (
            <button key={d.id} onClick={() => setSel(d.id)} className={cn("w-full rounded-xl border p-3 text-left text-sm transition", d.id === current ? "border-brand bg-brand-soft/50" : "border-border hover:bg-muted", d.status !== "ACTIVE" && "opacity-60")}>
              <p className="flex items-center gap-2 font-medium">{d.trust === "OFFICIAL" ? <FileText className="h-4 w-4 text-brand" /> : <ShieldAlert className="h-4 w-4 text-warn" />}{d.title}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5"><Badge>{d.source_id}</Badge><Badge>v{d.version}</Badge><Badge tone={d.status === "ACTIVE" ? "ok" : "muted"}>{d.status === "ACTIVE" ? "vigente" : "substituído"}</Badge><Badge tone={d.trust === "OFFICIAL" ? "brand" : "warn"}>{d.trust === "OFFICIAL" ? "oficial" : "não verificado"}</Badge></div>
              <p className="mt-1 text-xs text-subtle">{plural(d.sections, "seção", "seções")} · {fmt.dateTime(d.updated_at)}</p>
            </button>
          ))}
        </div>
        <Card className="p-6">{doc ? <Markdown text={doc.content} /> : <Skeleton className="h-64" />}</Card>
      </div>
      <Dialog wide open={upload} onClose={() => setUpload(false)} title="Publicar documento" description="Markdown com seções (## 1. Título, ### 1.1 Subtítulo). Publicar com um ID existente cria uma nova versão."
        footer={<><Button variant="ghost" onClick={() => setUpload(false)}>Cancelar</Button><Button loading={up.isPending} onClick={() => up.mutate()} disabled={!form.source_id || !form.title || form.content.length < 20}>Indexar</Button></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <div><Label>ID da fonte</Label><Input value={form.source_id} onChange={(e) => setForm({ ...form, source_id: e.target.value.toUpperCase() })} placeholder="REG-FACOM-2026" /></div>
          <div><Label>Confiabilidade</Label><Select value={form.trust} onChange={(e) => setForm({ ...form, trust: e.target.value })}><option value="OFFICIAL">Oficial</option><option value="UNVERIFIED">Não verificado</option></Select></div>
          <div className="sm:col-span-2"><Label>Título</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></div>
          <div className="sm:col-span-2"><Label>Conteúdo (Markdown)</Label><Textarea rows={12} className="font-mono text-xs" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} /></div>
        </div>
      </Dialog>
    </div>
  );
}
