// localStorage helpers. Storage can be unavailable (private mode, blocked site data): every access is
// wrapped so the app still works, just without remembering things. Nothing here is ever sent to a server.

export function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function safeSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
}

export function getJSON<T>(key: string, fallback: T): T {
  const raw = safeGet(key);
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function setJSON(key: string, value: unknown): void {
  safeSet(key, JSON.stringify(value));
}

// ---- recently viewed standards --------------------------------------------------------------------

export interface RecentStandard {
  slug: string;
  number: string | null;
  title: string;
  kind: string;
  at: number;
}

export function pushRecentStandard(s: Omit<RecentStandard, "at">): void {
  const list = getJSON<RecentStandard[]>("bisense.recentStandards", []).filter((x) => x.slug !== s.slug);
  list.unshift({ ...s, at: Date.now() });
  setJSON("bisense.recentStandards", list.slice(0, 8));
}

export const recentStandards = (): RecentStandard[] => getJSON<RecentStandard[]>("bisense.recentStandards", []);

// ---- recent questions (conversation history lives only in the browser) ------------------------------

export interface RecentQuestion {
  q: string;
  lang: string;
  at: number;
}

export function pushRecentQuestion(q: string, lang: string): void {
  const list = getJSON<RecentQuestion[]>("bisense.recentQuestions", []).filter((x) => x.q !== q);
  list.unshift({ q, lang, at: Date.now() });
  setJSON("bisense.recentQuestions", list.slice(0, 12));
}

export const recentQuestions = (): RecentQuestion[] => getJSON<RecentQuestion[]>("bisense.recentQuestions", []);

export function clearRecentQuestions(): void {
  setJSON("bisense.recentQuestions", []);
}
