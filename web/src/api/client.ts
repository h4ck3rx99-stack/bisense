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
  STTOut,
  VoiceStatus,
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

async function send(path: string, init?: RequestInit, json = true): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(path, json ? { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } } : init);
  } catch (e) {
    if ((e as { name?: string }).name === "AbortError") throw e;
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
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T;
}

const extFor = (type: string) => (type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : type.includes("mpeg") ? "mp3" : type.includes("wav") ? "wav" : "webm");

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
  voiceStatus: () => request<VoiceStatus>("/api/voice/status"),
  /** Speech-to-text on the server (multipart upload; the browser never sees a provider key). */
  stt: async (audio: Blob, lang: Lang, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("audio", audio, `speech.${extFor(audio.type)}`);
    form.append("lang", lang);
    return (await (await send("/api/voice/stt", { method: "POST", body: form, signal }, false)).json()) as STTOut;
  },
  /** Server text-to-speech for one chunk of text; returns audio (WAV). */
  tts: async (text: string, lang: Lang, signal?: AbortSignal) =>
    (await send("/api/voice/tts", { method: "POST", body: JSON.stringify({ text, lang }), signal })).blob(),
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
