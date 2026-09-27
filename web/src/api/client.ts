// Small typed fetch wrapper. Errors carry the server's stable `code` and i18n `message_key`.
import type {
  AskContext,
  CompareResponse,
  HealthOut,
  Lang,
  LibraryOut,
  RequirementsOut,
  SearchResponse,
  StandardDetail,
  StandardListOut,
  SuggestItem,
  SummaryOut,
  ClauseOut,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public messageKey: string,
  ) {
    super(code);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  } catch {
    throw new ApiError(0, "network", navigator.onLine ? "error.backend_down" : "error.offline");
  }
  if (!res.ok) {
    let body: { code?: string; message_key?: string } = {};
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, body.code ?? "http_error", body.message_key ?? (res.status >= 500 ? "error.internal" : "error.not_found"));
  }
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<HealthOut>("/api/health"),
  library: () => request<LibraryOut>("/api/library"),
  standards: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    });
    return request<StandardListOut>(`/api/standards?${qs.toString()}`);
  },
  suggest: (q: string, signal?: AbortSignal) => request<SuggestItem[]>(`/api/standards/suggest?q=${enc(q)}`, { signal }),
  standard: (slug: string) => request<StandardDetail>(`/api/standards/${enc(slug)}`),
  clause: (slug: string, number: string) => request<ClauseOut>(`/api/standards/${enc(slug)}/clauses/${enc(number)}`),
  clauses: (slug: string) => request<ClauseOut[]>(`/api/standards/${enc(slug)}/clauses`),
  requirements: (slug: string, params: { modality?: string; kind?: string; q?: string }) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v && qs.set(k, v));
    return request<RequirementsOut>(`/api/standards/${enc(slug)}/requirements?${qs.toString()}`);
  },
  plain: (slug: string, lang: Lang) => request<{ items: Record<string, string> }>(`/api/standards/${enc(slug)}/requirements/plain?lang=${lang}`),
  summary: (slug: string, lang: Lang) => request<SummaryOut>(`/api/standards/${enc(slug)}/summary?lang=${lang}`),
  search: (query: string, lang: Lang, context?: AskContext) =>
    request<SearchResponse>("/api/search", { method: "POST", body: JSON.stringify({ query, lang, context }) }),
  compare: (a: string, b: string, lang: Lang) => request<CompareResponse>("/api/compare", { method: "POST", body: JSON.stringify({ a, b, lang }) }),
  eval: () => request<EvalSummary>("/api/eval"),
};

export const csvUrl = (slug: string) => `/api/standards/${enc(slug)}/requirements.csv`;
export const pageImageUrl = (slug: string, page: number, highlight?: string) =>
  `/api/standards/${enc(slug)}/pages/${page}.png${highlight ? `?q=${enc(highlight.slice(0, 160))}` : ""}`;

export interface EvalSummary {
  available: boolean;
  generated_at?: string;
  dataset_mode?: string;
  corpus?: Record<string, number>;
  metrics?: Record<string, number | null>;
  targets?: Record<string, number>;
  counts?: Record<string, number>;
  llm?: string | null;
}
