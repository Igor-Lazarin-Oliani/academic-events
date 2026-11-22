import type { ReactNode } from "react";
import { Clock, MapPin, Mic2 } from "lucide-react";
import type { Session } from "@/lib/types";
import { cn, fmt, KIND_LABEL } from "@/lib/utils";
import { Badge, Progress } from "./ui";

const COVERS: Record<string, string> = {
  ACADEMIC: "from-[#3b4fd8] via-[#5b3fd0] to-[#9a3fc6]",
  HACKATHON: "from-[#0f766e] via-[#0e7490] to-[#1d4ed8]",
};

/** Capa gerada (sem imagens externas): gradiente por categoria + padrão geométrico. */
export function EventCover({ category, title, className, children }: { category: string; title: string; className?: string; children?: ReactNode }) {
  return (
    <div className={cn("relative overflow-hidden bg-gradient-to-br text-white", COVERS[category] ?? COVERS.ACADEMIC, className)}>
      <svg className="absolute inset-0 h-full w-full opacity-[0.18]" aria-hidden>
        <defs>
          <pattern id={`p-${category}`} width="44" height="44" patternUnits="userSpaceOnUse">
            <path d="M0 22h44M22 0v44" stroke="white" strokeWidth="0.6" />
            <circle cx="22" cy="22" r="3" fill="white" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#p-${category})`} />
      </svg>
      <div className="absolute -right-10 -top-16 h-56 w-56 rounded-full bg-white/10 blur-2xl" />
      <span className="sr-only">{title}</span>
      <div className="relative">{children}</div>
    </div>
  );
}

const KIND_TONE: Record<string, "brand" | "accent" | "ok" | "warn" | "muted"> = { MINICURSO: "accent", PALESTRA: "brand", WORKSHOP: "ok", MESA_REDONDA: "warn", ABERTURA: "muted" };

export function SessionMeta({ s }: { s: Session }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-subtle">
      <span className="flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" />{fmt.weekdayShort(s.start_at)} {fmt.date(s.start_at)} · {fmt.range(s.start_at, s.end_at)}</span>
      {s.room && <span className="flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" />{s.room.name}</span>}
      {s.speakers.length > 0 && <span className="flex items-center gap-1.5"><Mic2 className="h-3.5 w-3.5" />{s.speakers.map((p) => p.name).join(", ")}</span>}
    </div>
  );
}

export function SessionBadges({ s }: { s: Session }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Badge tone={KIND_TONE[s.kind] ?? "muted"}>{KIND_LABEL[s.kind] ?? s.kind}</Badge>
      <Badge tone="muted">{s.track}</Badge>
      <Badge tone="muted">{s.workload_hours}h de certificado</Badge>
      {s.status === "SOLD_OUT" && <Badge tone="danger">Esgotada</Badge>}
      {s.status === "CANCELLED" && <Badge tone="danger">Cancelada</Badge>}
    </div>
  );
}

export function Occupancy({ s }: { s: Session }) {
  const occ = s.max_capacity - s.available_spots;
  const rate = occ / s.max_capacity;
  return (
    <div className="w-full">
      <div className="mb-1 flex justify-between text-xs text-subtle">
        <span>{s.available_spots > 0 ? `${s.available_spots} vaga${s.available_spots > 1 ? "s" : ""}` : "sem vagas"}</span>
        <span>{occ}/{s.max_capacity}</span>
      </div>
      <Progress value={rate} tone={rate >= 1 ? "danger" : rate > 0.85 ? "warn" : "brand"} />
    </div>
  );
}

/** Normaliza texto vindo do modelo: alguns modelos devolvem "\n" literal em vez de quebra de linha. */
export function normalizeModelText(text: string): string {
  const BS = String.fromCharCode(92); // barra invertida
  return (text ?? "")
    .split(BS + "r" + BS + "n").join("\n") // quebra de linha literal vinda do modelo
    .split(BS + "n").join("\n")
    .split(BS + "t").join(" ")
    .replace(/\r\n/g, "\n");
}

/** Renderizador mínimo e seguro de Markdown (sem HTML): títulos, listas, parágrafos, **negrito**, *itálico*, `código`.
 *  compact = espaçamento de balão de chat. */
export function Markdown({ text, compact = false }: { text: string; compact?: boolean }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const pCls = compact ? "my-1 first:mt-0 last:mb-0 leading-relaxed" : "my-1.5 text-sm leading-relaxed";
  const flush = () => {
    if (list?.items.length) {
      const cls = cn(list.ordered ? "list-decimal" : "list-disc", compact ? "my-1.5 space-y-1 pl-5 first:mt-0 last:mb-0" : "my-2 space-y-1 pl-5");
      const items = list.items.map((l, i) => <li key={i} className="pl-0.5">{inline(l)}</li>);
      blocks.push(list.ordered ? <ol key={blocks.length} className={cls}>{items}</ol> : <ul key={blocks.length} className={cls}>{items}</ul>);
    }
    list = null;
  };
  normalizeModelText(text).split("\n").forEach((raw) => {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const ordered = !!numbered;
      if (!list || list.ordered !== ordered) { flush(); list = { ordered, items: [] }; }
      list.items.push((bullet ?? numbered)![1]);
      return;
    }
    flush();
    if (!line.trim()) return;
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      const lvl = h[1].length;
      blocks.push(compact ? <p key={blocks.length} className={cn(pCls, "font-semibold")}>{inline(h[2])}</p>
        : lvl === 1 ? <h2 key={blocks.length} className="mb-2 mt-1 text-xl font-bold">{h[2]}</h2>
        : lvl === 2 ? <h3 key={blocks.length} className="mb-1 mt-5 text-base font-semibold">{h[2]}</h3>
        : <h4 key={blocks.length} className="mb-1 mt-3 text-sm font-semibold text-subtle">{h[2]}</h4>);
      return;
    }
    blocks.push(<p key={blocks.length} className={pCls}>{inline(line)}</p>);
  });
  flush();
  return <div>{blocks}</div>;
}

function inline(s: string): ReactNode {
  // **negrito**, *itálico* / _itálico_ e `código`; o restante é texto puro (sem HTML).
  const parts = s.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|(?<![\w])_[^_\s][^_]*_(?![\w]))/g);
  return parts.map((p, i) => {
    if (!p) return null;
    if (p.startsWith("**") && p.endsWith("**") && p.length > 4) return <strong key={i} className="font-semibold">{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`") && p.length > 2) return <code key={i} className="rounded bg-muted px-1 text-xs">{p.slice(1, -1)}</code>;
    if (((p.startsWith("*") && p.endsWith("*")) || (p.startsWith("_") && p.endsWith("_"))) && p.length > 2) return <em key={i}>{p.slice(1, -1)}</em>;
    return p;
  });
}
