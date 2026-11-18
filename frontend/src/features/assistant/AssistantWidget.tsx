import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronDown, ExternalLink, MessageCircle, Send, Sparkles, X } from "lucide-react";
import { api, streamPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ChatResult, Evidence, EventSummary, Step } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";
import { Markdown } from "@/components/shared";
import { ProposalCard } from "./ProposalCard";
import { Timeline } from "./timeline";

interface Msg { role: "user" | "assistant"; content: string; result?: Partial<ChatResult>; steps?: Step[]; pending?: boolean }

const SUGGESTIONS = [
  "Quantas horas vale o certificado de um minicurso?",
  "Em quais sessões estou inscrito?",
  "Quero trocar o minicurso de React pelo de LLMs e RAG",
  "Onde e quando é a palestra de Kubernetes?",
];

const SOURCE_LABEL: Record<string, string> = { PROGRAMACAO: "Programação", MEUS_INGRESSOS: "Seus ingressos" };

export function EvidenceChips({ evidence }: { evidence: Evidence[] }) {
  if (!evidence?.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {evidence.map((e, i) => (
        <span key={i} title={e.title ?? ""} className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
          e.trust === "UNVERIFIED" ? "border-warn/40 text-warn" : "border-border bg-surface text-subtle")}>
          <BookOpen className="h-3 w-3" />
          {SOURCE_LABEL[e.source_id] ?? e.source_id}{e.section ? ` · ${e.section}` : ""}
        </span>
      ))}
    </div>
  );
}

export function AssistantWidget({ eventSlug }: { eventSlug?: string }) {
  const { user, isManager } = useAuth();
  const [open, setOpen] = useState(false);
  const { data: events = [] } = useQuery({ queryKey: ["events"], queryFn: () => api<EventSummary[]>("/events") });
  const event = events.find((e) => e.slug === eventSlug) ?? events.find((e) => e.status === "PUBLISHED");
  const storeKey = event ? `ae.conv.${user?.id}.${event.slug}` : "";
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  useEffect(() => {
    if (!storeKey) return;
    let id: string | null = null;
    try { id = localStorage.getItem(storeKey); } catch { /* ignore */ }
    setConversationId(id);
    setMessages([]);
    if (id) {
      api<any[]>(`/assistant/conversations/${id}/messages`).then((rows) =>
        setMessages(rows.map((r) => ({ role: r.role, content: r.content, result: r.payload ? { evidence: r.payload.evidence, proposals: r.payload.proposals, kind: r.payload.kind, run_id: r.run_id } : undefined }))),
      ).catch(() => setConversationId(null));
    }
  }, [storeKey]);

  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [messages, open]);

  async function send(text: string) {
    if (!text.trim() || !event || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "", steps: [], pending: true }]);
    const patchLast = (fn: (m: Msg) => Msg) => setMessages((ms) => ms.map((m, i) => (i === ms.length - 1 ? fn(m) : m)));
    await streamPost("/assistant/chat", { event_id: event.slug, message: text, conversation_id: conversationId }, {
      onStep: (s) => patchLast((m) => ({ ...m, steps: [...(m.steps ?? []), s] })),
      onResult: (r: ChatResult) => {
        patchLast((m) => ({ ...m, content: r.answer, result: r, pending: false }));
        if (r.conversation_id && r.conversation_id !== conversationId) {
          setConversationId(r.conversation_id);
          try { localStorage.setItem(storeKey, r.conversation_id); } catch { /* ignore */ }
        }
        qc.invalidateQueries({ queryKey: ["notifications"] });
      },
      onError: (e) => patchLast((m) => ({ ...m, content: e.message ?? "Não consegui responder agora.", pending: false, result: { kind: "error" } })),
    }).catch((e) => patchLast((m) => ({ ...m, content: String(e), pending: false })));
    setBusy(false);
  }

  function reset() {
    setConversationId(null);
    setMessages([]);
    try { localStorage.removeItem(storeKey); } catch { /* ignore */ }
  }

  if (!event) return null;
  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)} className="fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full bg-brand px-5 py-3.5 font-medium text-brand-fg shadow-xl transition hover:scale-[1.03]">
          <Sparkles className="h-5 w-5" /> <span className="hidden sm:inline">Pergunte ao assistente</span>
        </button>
      )}
      {open && (
        <div className="fixed inset-0 z-50 flex flex-col bg-surface sm:inset-auto sm:bottom-5 sm:right-5 sm:h-[640px] sm:max-h-[calc(100vh-40px)] sm:w-[420px] sm:rounded-2xl sm:border sm:border-border sm:shadow-2xl animate-fade-in">
          <div className="flex items-center gap-3 border-b border-border px-4 py-3">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-brand text-brand-fg"><Sparkles className="h-4 w-4" /></span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">Assistente do evento</p>
              <p className="truncate text-xs text-subtle">{event.title} · respostas com fonte</p>
            </div>
            {messages.length > 0 && <Button variant="ghost" size="sm" onClick={reset}>Nova conversa</Button>}
            <Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label="Fechar"><X className="h-4 w-4" /></Button>
          </div>
          <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto px-4 py-4 scrollbar-thin">
            {messages.length === 0 && (
              <div className="pt-6 text-center">
                <MessageCircle className="mx-auto h-10 w-10 text-brand" />
                <p className="mt-3 font-semibold">Olá, {user?.name.split(" ")[0]}! Como posso ajudar?</p>
                <p className="mx-auto mt-1 max-w-xs text-sm text-subtle">Respondo com base no regulamento, na programação e nos seus ingressos. Ações como cancelar ou trocar sempre pedem sua confirmação.</p>
                <div className="mt-5 flex flex-col gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)} className="rounded-xl border border-border px-3 py-2 text-left text-sm hover:border-brand/50 hover:bg-brand-soft/40">{s}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (m.role === "user" ? (
              <div key={i} className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand px-3.5 py-2 text-sm text-brand-fg">{m.content}</div></div>
            ) : (
              <AssistantMessage key={i} msg={m} canInspect={isManager} />
            )))}
          </div>
          <form className="flex gap-2 border-t border-border p-3" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} placeholder="Escreva sua dúvida…" maxLength={2000}
              className="h-11 flex-1 rounded-xl border border-border bg-bg px-3.5 text-sm focus:border-brand focus:outline-none" />
            <Button type="submit" size="icon" className="h-11 w-11 rounded-xl" disabled={!input.trim() || busy} aria-label="Enviar"><Send className="h-4 w-4" /></Button>
          </form>
        </div>
      )}
    </>
  );
}

function AssistantMessage({ msg, canInspect }: { msg: Msg; canInspect: boolean }) {
  const [showSteps, setShowSteps] = useState(false);
  const r = msg.result ?? {};
  const degraded = r.kind === "degraded" || r.kind === "error";
  return (
    <div className="flex gap-2">
      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand-soft text-brand"><Sparkles className="h-3.5 w-3.5" /></span>
      <div className="min-w-0 flex-1">
        {msg.pending ? (
          <div className="rounded-2xl rounded-tl-md bg-muted px-3.5 py-3">
            <Timeline steps={msg.steps ?? []} dense live />
          </div>
        ) : (
          <div className={cn("rounded-2xl rounded-tl-md px-3.5 py-2.5 text-sm", degraded ? "bg-warn/10" : "bg-muted")}>
            <Markdown text={msg.content} compact />
            <EvidenceChips evidence={r.evidence ?? []} />
          </div>
        )}
        {!msg.pending && (r.proposals ?? []).length > 0 && (
          <div className="mt-2 space-y-2">{r.proposals!.map((p) => <ProposalCard key={p.id} proposal={p} />)}</div>
        )}
        {!msg.pending && (msg.steps?.length || r.run_id) ? (
          <div className="mt-1 flex items-center gap-3 px-1">
            {!!msg.steps?.length && (
              <button className="flex items-center gap-1 text-[11px] text-subtle hover:text-fg" onClick={() => setShowSteps((s) => !s)}>
                <ChevronDown className={cn("h-3 w-3 transition", showSteps && "rotate-180")} />como cheguei a esta resposta ({msg.steps.filter((s) => s.type === "tool.result").length} consultas)
              </button>
            )}
            {canInspect && r.run_id && <Link to={`/painel/trajetorias/${r.run_id}`} className="flex items-center gap-1 text-[11px] text-subtle hover:text-fg"><ExternalLink className="h-3 w-3" />trajetória</Link>}
          </div>
        ) : null}
        {showSteps && <div className="mt-2 rounded-xl border border-border p-3"><Timeline steps={msg.steps ?? []} dense /></div>}
      </div>
    </div>
  );
}
