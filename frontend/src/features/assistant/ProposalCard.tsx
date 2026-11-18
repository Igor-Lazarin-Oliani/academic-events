import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import { api, friendlyError } from "@/lib/api";
import type { Proposal, ProposalCard as Card } from "@/lib/types";
import { Badge, Button, useToast } from "@/components/ui";

/** Cartão de confirmação L2: o agente PROPÔS; quem decide é o próprio participante, aqui, fora do chat. */
export function ProposalCard({ proposal, onDecided }: { proposal: Card; onDecided?: (p: Proposal) => void }) {
  const [status, setStatus] = useState(proposal.status);
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();
  const toast = useToast();

  async function decide(action: "approve" | "reject") {
    setBusy(action);
    setError(null);
    try {
      const p = await api<Proposal>(`/proposals/${proposal.id}/${action}`, { method: "POST", body: {} });
      setStatus(p.status);
      if (p.status === "FAILED") setError(p.error ?? "Não foi possível executar.");
      else toast({ kind: action === "approve" ? "success" : "info", title: action === "approve" ? "Feito!" : "Solicitação descartada", description: action === "approve" ? proposal.title : undefined });
      qc.invalidateQueries({ queryKey: ["my-tickets"] });
      qc.invalidateQueries({ queryKey: ["event"] });
      qc.invalidateQueries({ queryKey: ["my-proposals"] });
      onDecided?.(p);
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  const imp = proposal.impact ?? {};
  return (
    <div className="rounded-xl border border-brand/30 bg-brand-soft/40 p-3.5">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-brand" />
        <p className="text-xs font-semibold uppercase tracking-wide text-brand">Precisa da sua confirmação</p>
        <Badge tone="muted" className="ml-auto">{proposal.level}</Badge>
      </div>
      <p className="mt-2 text-sm font-semibold">{proposal.title}</p>
      {proposal.kind === "SWAP_SESSION" && imp.from && imp.to ? (
        <div className="mt-2 flex items-center gap-2 text-xs">
          <span className="rounded-lg bg-surface px-2 py-1 line-through decoration-danger/60">{imp.from.code} · {imp.from.when}</span>
          <ArrowRight className="h-3.5 w-3.5 shrink-0 text-subtle" />
          <span className="rounded-lg bg-surface px-2 py-1 font-medium">{imp.to.code} · {imp.to.when}</span>
        </div>
      ) : (
        <p className="mt-1 text-xs text-subtle">{proposal.summary}</p>
      )}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      <div className="mt-3 flex gap-2">
        {status === "PENDING" ? (
          <>
            <Button size="sm" onClick={() => decide("approve")} loading={busy === "approve"} disabled={!!busy}>Confirmar</Button>
            <Button size="sm" variant="ghost" onClick={() => decide("reject")} loading={busy === "reject"} disabled={!!busy}>Agora não</Button>
          </>
        ) : status === "EXECUTED" ? (
          <p className="flex items-center gap-1.5 text-sm font-medium text-ok"><CheckCircle2 className="h-4 w-4" />Confirmado e aplicado</p>
        ) : status === "REJECTED" ? (
          <p className="flex items-center gap-1.5 text-sm text-subtle"><XCircle className="h-4 w-4" />Descartado</p>
        ) : (
          <p className="text-sm text-danger">{status}</p>
        )}
      </div>
    </div>
  );
}
