import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Bot, CheckCircle2, HelpCircle, Siren, Sparkles } from "lucide-react";
import { streamPost } from "@/lib/api";
import type { Step } from "@/lib/types";
import { plural } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, PageHeader, Textarea } from "@/components/ui";
import { usePanelEvent } from "@/components/layout/PanelLayout";
import { Timeline } from "@/features/assistant/timeline";
import { Markdown } from "@/components/shared";
import { PlanSteps, ReviewBox } from "./ApprovalsPage";

const EXAMPLES = [
  "A Dra. Helena Duarte avisou que não vai conseguir dar a palestra de quinta à tarde. Ela pode na sexta de manhã.",
  "A Sala 105 ficou sem energia na quarta-feira de manhã e só volta depois do meio-dia.",
  "O LIA-2 vai ficar fechado na terça à tarde para manutenção dos computadores.",
];

const GRAPH = ["INVESTIGATE", "VALIDATE", "REVIEW", "PROPOSE", "HUMAN_APPROVAL"];
const GRAPH_LABEL: Record<string, string> = { INVESTIGATE: "Investigar", VALIDATE: "Validar", REVIEW: "Revisar", PROPOSE: "Propor", HUMAN_APPROVAL: "Aprovação humana" };

export function IncidentsPage() {
  const { event } = usePanelEvent();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [steps, setSteps] = useState<Step[]>([]);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const timelineRef = useRef<HTMLDivElement>(null);

  // acompanha o último passo enquanto o agente trabalha (rola só dentro do painel, nunca a página)
  useEffect(() => {
    const el = timelineRef.current;
    if (el && running) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [steps.length, running]);

  const nodes = steps.filter((s) => s.type === "transition").map((s) => s.name.split("->")[1]);
  const current = result ? result.node : nodes.at(-1) ?? (running ? "INVESTIGATE" : null);
  const visited = new Set(["INVESTIGATE", ...nodes]);
  const revisions = steps.filter((s) => s.type === "handoff").length;

  async function run() {
    setSteps([]); setResult(null); setError(null); setRunning(true);
    await streamPost("/operations/incidents", { event_id: event!.id, incident: text }, {
      onStep: (s) => setSteps((xs) => [...xs, s]),
      onResult: (r) => { setResult(r); qc.invalidateQueries({ queryKey: ["proposals"] }); },
      onError: (e) => setError(e.message),
    }).catch((e) => setError(String(e)));
    setRunning(false);
  }

  const draft = result?.draft;
  return (
    <div>
      <PageHeader eyebrow="Agente de Operações" title="Ocorrências" description="Descreva o imprevisto em linguagem natural. O agente investiga o impacto no grafo do evento, busca alternativas reais, valida o plano e o Revisor confere o comunicado. Nada é aplicado sem a sua aprovação." />
      <div className="grid gap-6 xl:grid-cols-[1fr_1.1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="O que aconteceu?" />
            <CardBody>
              <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder="Ex.: o palestrante da sessão de quinta cancelou…" disabled={running} />
              <div className="mt-3 flex flex-wrap gap-2">
                {EXAMPLES.map((ex) => <button key={ex} onClick={() => setText(ex)} disabled={running} className="rounded-full border border-border px-3 py-1 text-left text-xs text-subtle hover:border-brand/50 hover:text-fg">{ex.slice(0, 60)}…</button>)}
              </div>
              <div className="mt-4 flex justify-end"><Button onClick={run} loading={running} disabled={text.trim().length < 10}><Siren className="h-4 w-4" />Analisar ocorrência</Button></div>
            </CardBody>
          </Card>

          {(running || result) && (
            <Card>
              <CardHeader title="Orquestração" description="Grafo de estados com checkpoint a cada transição" />
              <CardBody>
                <div className="flex flex-wrap items-center gap-1.5">
                  {GRAPH.map((n, i) => (
                    <div key={n} className="flex items-center gap-1.5">
                      <span className={`rounded-lg border px-2.5 py-1 text-xs font-medium ${current === n ? "border-brand bg-brand text-brand-fg" : visited.has(n) && (result || n !== current) ? "border-brand/30 bg-brand-soft text-brand" : "border-border text-subtle"}`}>{GRAPH_LABEL[n]}</span>
                      {i < GRAPH.length - 1 && <ArrowRight className="h-3 w-3 text-subtle" />}
                    </div>
                  ))}
                </div>
                {revisions > 0 && <p className="mt-3 text-xs text-warn">↺ {plural(revisions, "revisão", "revisões")}: o Revisor devolveu o comunicado ao agente</p>}
              </CardBody>
            </Card>
          )}

          {result && (
            <Card className="animate-fade-in">
              {result.status === "WAITING_APPROVAL" && draft ? (
                <>
                  <CardHeader title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-brand" />Plano proposto</span>} description="Enviado para a Central de Aprovações"
                    action={<Link to="/painel/aprovacoes"><Button size="sm">Revisar e aprovar</Button></Link>} />
                  <CardBody className="space-y-4">
                    <p className="text-sm">{draft.diagnosis}</p>
                    {draft.rationale && <p className="text-sm text-subtle">{draft.rationale}</p>}
                    <PlanSteps changes={result.proposal?.impact?.changes ?? []} />
                    {draft.communication && (
                      <div className="rounded-xl border border-border bg-muted/40 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-subtle">Comunicado para {plural(result.proposal?.impact?.recipients ?? 0, "inscrito", "inscritos")}</p>
                        <p className="mt-2 text-sm font-semibold">{draft.communication.title}</p>
                        <div className="mt-1 text-sm"><Markdown text={draft.communication.body} compact /></div>
                      </div>
                    )}
                    {result.review && <ReviewBox review={result.review} />}
                  </CardBody>
                </>
              ) : draft?.kind === "need_info" ? (
                <CardBody className="flex gap-3 pt-5"><HelpCircle className="h-5 w-5 shrink-0 text-brand" /><div><p className="font-semibold">O agente precisa de mais informação</p><p className="mt-1 text-sm">{draft.question}</p><p className="mt-2 text-xs text-subtle">{draft.diagnosis}</p></div></CardBody>
              ) : draft ? (
                <CardBody className="flex gap-3 pt-5"><CheckCircle2 className="h-5 w-5 shrink-0 text-ok" /><div><p className="font-semibold">{draft.kind === "no_action" ? "Nenhuma mudança necessária" : "Pedido recusado"}</p><p className="mt-1 text-sm text-subtle">{draft.diagnosis}</p></div></CardBody>
              ) : (
                <CardBody className="flex gap-3 pt-5"><AlertTriangle className="h-5 w-5 shrink-0 text-warn" /><div><p className="font-semibold">Não foi possível concluir ({result.status})</p><p className="mt-1 text-sm text-subtle">{result.error ?? "O agente está indisponível no momento. Você pode alterar a programação manualmente."}</p></div></CardBody>
              )}
            </Card>
          )}
          {error && <Card className="border-danger/40 p-4 text-sm text-danger">{error}</Card>}
        </div>

        {/* Painel fixo: ocupa toda a altura visível abaixo do cabeçalho e não se move ao rolar.
            O <main> do painel é o contêiner de rolagem, então top-0 encosta logo abaixo do cabeçalho;
            só a lista de passos rola por dentro. */}
        <Card className="flex max-h-[75vh] flex-col xl:sticky xl:top-0 xl:h-[calc(100vh-7rem)] xl:max-h-none xl:self-start">
          <CardHeader className="shrink-0" title={<span className="flex items-center gap-2"><Bot className="h-4 w-4" />Trajetória ao vivo</span>} description="Cada decisão do modelo, cada consulta, cada guardrail"
            action={result?.run_id && <Link to={`/painel/trajetorias/${result.run_id}`}><Badge tone="brand">detalhes</Badge></Link>} />
          <CardBody ref={timelineRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain scrollbar-thin">
            {steps.length === 0 && !running ? <p className="py-10 text-center text-sm text-subtle">A trajetória aparece aqui quando o agente começar.</p> : <Timeline steps={steps} live={running} />}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
