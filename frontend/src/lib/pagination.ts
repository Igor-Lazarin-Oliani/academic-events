import { useEffect, useState } from "react";

/** Tamanho de página padrão das listagens do painel. */
export const PAGE_SIZE = 50;

/** Valor atrasado: evita disparar uma consulta a cada tecla digitada na busca. */
export function useDebounced<T>(value: T, delay = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

/**
 * Página atual de uma listagem. Volta para a primeira página sempre que `resetKey` (os filtros) muda.
 * O reset acontece durante o render, então a consulta já sai com offset 0, sem buscar a página antiga.
 */
export function usePagination(resetKey: string, pageSize = PAGE_SIZE) {
  const [page, setPage] = useState(0);
  const [key, setKey] = useState(resetKey);
  if (key !== resetKey) {
    setKey(resetKey);
    setPage(0);
  }
  return { page, setPage, pageSize, limit: pageSize, offset: page * pageSize };
}

/** Monta a query string com filtros (ignorando vazios) + limit/offset. */
export function pageQuery(filters: Record<string, string | undefined | null>, pg?: { limit: number; offset: number }) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) if (v) qs.set(k, v);
  if (pg) { qs.set("limit", String(pg.limit)); qs.set("offset", String(pg.offset)); }
  return qs;
}
