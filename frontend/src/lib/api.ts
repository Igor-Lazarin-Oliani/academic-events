const BASE = "/api";
const TOKEN_KEY = "ae.token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token: string | null) {
  try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch { /* armazenamento indisponível */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public details?: any) { super(message); }
}

const MESSAGES: Record<string, string> = {
  sold_out: "Esta sessão está esgotada.",
  time_conflict: "Você já tem uma inscrição nesse horário.",
  minicurso_limit: "Você atingiu o limite de minicursos deste evento.",
  already_registered: "Você já está inscrito nesta sessão.",
  already_cancelled: "Este ingresso já foi cancelado.",
  already_checked_in: "Ingressos com check-in não podem ser cancelados.",
  invalid_status: "Este ingresso não pode fazer check-in (já usado ou cancelado).",
  session_ended: "Esta sessão já terminou.",
  ticket_out_of_scope: "Este ingresso não pertence a este evento ou a você.",
  event_out_of_scope: "Você não gerencia este evento.",
  proposal_not_pending: "Esta solicitação já foi decidida.",
  not_found: "Não encontrado.",
  unauthorized: "Sua sessão expirou. Entre novamente.",
};

export function friendlyError(e: unknown): string {
  if (e instanceof ApiError) return (e.code && MESSAGES[e.code]) || e.message;
  return e instanceof Error ? e.message : "Erro inesperado.";
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any; signal?: AbortSignal } = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(BASE + path, {
    method: opts.method ?? (opts.body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-Correlation-Id": `ui-${crypto.randomUUID().slice(0, 12)}`, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error ?? {};
    const detail = Array.isArray(data?.detail) ? data.detail.map((d: any) => d.msg).join("; ") : data?.detail;
    if (res.status === 401) setToken(null);
    throw new ApiError(res.status, err.message ?? detail ?? `Erro ${res.status}`, err.code, err.details);
  }
  return data as T;
}

/** GET autenticado que baixa a resposta como arquivo (ex.: exportação CSV gerada no servidor). */
export async function apiDownload(path: string, filename: string): Promise<void> {
  const token = getToken();
  const res = await fetch(BASE + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, data?.error?.message ?? `Erro ${res.status}`, data?.error?.code);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** POST com resposta em Server-Sent Events (trajetória do agente ao vivo). */
export async function streamPost(path: string, body: any, handlers: { onStep?: (s: any) => void; onResult?: (r: any) => void; onError?: (e: any) => void }, signal?: AbortSignal) {
  const token = getToken();
  const res = await fetch(BASE + path + (path.includes("?") ? "&" : "?") + "stream=true", {
    method: "POST", signal,
    headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => null);
    handlers.onError?.(new ApiError(res.status, data?.error?.message ?? `Erro ${res.status}`, data?.error?.code));
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message", data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const parsed = JSON.parse(data);
      if (event === "step") handlers.onStep?.(parsed);
      else if (event === "result") handlers.onResult?.(parsed);
      else if (event === "error") handlers.onError?.(new ApiError(parsed.status ?? 500, parsed.message, parsed.code));
    }
  }
}
