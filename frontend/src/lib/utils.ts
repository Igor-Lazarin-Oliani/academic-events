import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const TZ = "America/Campo_Grande";
const dFmt = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, day: "2-digit", month: "2-digit" });
const wFmt = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, weekday: "long" });
const wShort = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, weekday: "short" });
const tFmt = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const longFmt = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, day: "numeric", month: "long" });
const dtFmt = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const keyFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });

export const fmt = {
  date: (s: string) => dFmt.format(new Date(s)),
  weekday: (s: string) => wFmt.format(new Date(s)),
  weekdayShort: (s: string) => wShort.format(new Date(s)).replace(".", ""),
  time: (s: string) => tFmt.format(new Date(s)).replace(":", "h"),
  long: (s: string) => longFmt.format(new Date(s)),
  dateTime: (s: string) => dtFmt.format(new Date(s)),
  dayKey: (s: string) => keyFmt.format(new Date(s)),
  range: (a: string, b: string) => `${tFmt.format(new Date(a)).replace(":", "h")}–${tFmt.format(new Date(b)).replace(":", "h")}`,
  period: (a: string, b: string) => `${longFmt.format(new Date(a))} a ${longFmt.format(new Date(b))}`,
  relative: (s: string) => {
    const diff = (Date.now() - new Date(s).getTime()) / 1000;
    if (diff < 60) return "agora";
    if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
    return dtFmt.format(new Date(s));
  },
  duration: (ms: number | null | undefined) => (ms == null ? "" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`),
};

export const KIND_LABEL: Record<string, string> = {
  PALESTRA: "Palestra", MINICURSO: "Minicurso", MESA_REDONDA: "Mesa-redonda", WORKSHOP: "Workshop", ABERTURA: "Plenária",
};

export const TICKET_STATUS: Record<string, { label: string; tone: "ok" | "brand" | "muted" | "danger" | "warn" }> = {
  CONFIRMED: { label: "Confirmado", tone: "brand" },
  CHECKED_IN: { label: "Presença registrada", tone: "ok" },
  CANCELLED: { label: "Cancelado", tone: "muted" },
};

export function initials(name: string) {
  return name.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

export function downloadCsv(filename: string, rows: (string | number)[][]) {
  const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(";")).join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** Escolhe a forma singular ou plural conforme a quantidade (concordância nominal). */
export function pluralWord(n: number, singular: string, plural: string) {
  return Math.abs(n) === 1 ? singular : plural;
}

/** Quantidade + palavra concordando: plural(1, "inscrito", "inscritos") → "1 inscrito". */
export function plural(n: number, singular: string, plural: string) {
  return `${n.toLocaleString("pt-BR")} ${pluralWord(n, singular, plural)}`;
}
