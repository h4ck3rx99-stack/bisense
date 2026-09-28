// Read-aloud for answers. One player for the whole app, so starting a new answer, asking a new question,
// changing page or changing language always stops what is playing.
//
// Engines, in order: the browser's own voice for the language (instant, offline), then the server voice
// (/api/voice/tts) for languages the server supports. If neither exists — typical for Kannada on desktop
// browsers — the UI says so; it never plays English audio for Hindi/Kannada text.
//
// Browser quirks handled: getVoices() is empty until "voiceschanged" fires (Chrome); long utterances
// stop after ~15 s in Chrome, so text is spoken sentence by sentence; cancel() fires onerror("interrupted").

import { useSyncExternalStore } from "react";
import { api } from "../api/client";
import type { Lang } from "../api/types";

export type TtsState = "idle" | "loading" | "speaking" | "error";
export type TtsEngine = "browser" | "server" | "none";

const LOCALES: Record<Lang, string> = { en: "en-IN", hi: "hi-IN", kn: "kn-IN" };

export const browserTtsSupported = (): boolean => typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

/** Voices, waiting (up to `timeoutMs`) for Chrome's asynchronous voice list. */
export function loadVoices(timeoutMs = 1500): Promise<SpeechSynthesisVoice[]> {
  if (!browserTtsSupported()) return Promise.resolve([]);
  const synth = window.speechSynthesis;
  const now = synth.getVoices();
  if (now.length) return Promise.resolve(now);
  return new Promise((resolve) => {
    const done = () => {
      synth.removeEventListener("voiceschanged", done);
      window.clearTimeout(timer);
      resolve(synth.getVoices());
    };
    const timer = window.setTimeout(done, timeoutMs);
    synth.addEventListener("voiceschanged", done);
  });
}

/** Best installed voice for a language: exact locale, then any voice of that language. Never a different language. */
export function pickVoice(voices: SpeechSynthesisVoice[], lang: Lang): SpeechSynthesisVoice | null {
  const locale = LOCALES[lang].toLowerCase();
  const norm = (v: SpeechSynthesisVoice) => v.lang.replace("_", "-").toLowerCase();
  return voices.find((v) => norm(v) === locale) ?? voices.find((v) => norm(v).split("-")[0] === lang) ?? null;
}

/** Split into sentence groups of at most `max` characters (Devanagari danda and Kannada use "।" / "."). */
export function splitSentences(text: string, max = 220): string[] {
  const sentences = text
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?।॥])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const out: string[] = [];
  for (const s of sentences) {
    if (s.length > max) {
      // very long sentence: break at commas/semicolons, then hard-wrap on spaces
      let rest = s;
      while (rest.length > max) {
        let cut = Math.max(rest.lastIndexOf(", ", max), rest.lastIndexOf("; ", max));
        if (cut < max / 3) cut = rest.lastIndexOf(" ", max);
        if (cut <= 0) cut = max;
        out.push(rest.slice(0, cut + 1).trim());
        rest = rest.slice(cut + 1).trim();
      }
      if (rest) out.push(rest);
    } else if (out.length && (out[out.length - 1] + " " + s).length <= max) {
      out[out.length - 1] += " " + s;
    } else {
      out.push(s);
    }
  }
  return out;
}

interface Snapshot {
  state: TtsState;
  id: string | null; // which answer is playing
  engine: TtsEngine;
  error: string | null; // i18n key suffix: "unavailable_lang" | "failed"
}

let snap: Snapshot = { state: "idle", id: null, engine: "none", error: null };
const listeners = new Set<() => void>();
let run = 0; // incremented by stop(); a stale run never touches state
let audio: HTMLAudioElement | null = null;
let abort: AbortController | null = null;
let keepAlive = 0;
let serverLangs: Lang[] = [];

function set(next: Partial<Snapshot>) {
  snap = { ...snap, ...next };
  listeners.forEach((l) => l());
}

/** Languages the server can speak (from /api/voice/status), set once at startup. */
export function setServerTtsLanguages(langs: string[]) {
  serverLangs = langs.filter((l): l is Lang => l === "en" || l === "hi" || l === "kn");
}

/** Which engine would speak this language on this device (after voices have loaded). */
export async function engineFor(lang: Lang): Promise<TtsEngine> {
  if (pickVoice(await loadVoices(), lang)) return "browser";
  if (serverLangs.includes(lang)) return "server";
  return "none";
}

export function stopSpeaking(): void {
  run++;
  window.clearInterval(keepAlive);
  abort?.abort();
  abort = null;
  if (audio) {
    audio.pause();
    audio.src = "";
    audio = null;
  }
  if (browserTtsSupported()) window.speechSynthesis.cancel();
  if (snap.state !== "idle" || snap.id) set({ state: "idle", id: null, error: null });
}

export async function speakText(id: string, text: string, lang: Lang): Promise<void> {
  stopSpeaking();
  const mine = ++run;
  set({ state: "loading", id, error: null });
  const engine = await engineFor(lang);
  if (mine !== run) return;
  if (engine === "none") {
    set({ state: "error", engine, error: "unavailable_lang" });
    return;
  }
  set({ engine });
  const chunks = splitSentences(text, engine === "server" ? 380 : 220);
  try {
    if (engine === "browser") await speakBrowser(chunks, lang, mine);
    else await speakServer(chunks, lang, mine);
    if (mine === run) set({ state: "idle", id: null });
  } catch {
    if (mine !== run) return;
    // Browser voice failed: try the server voice once before giving up.
    if (engine === "browser" && serverLangs.includes(lang)) {
      try {
        set({ engine: "server" });
        await speakServer(splitSentences(text, 380), lang, mine);
        if (mine === run) set({ state: "idle", id: null });
        return;
      } catch {
        /* fall through */
      }
    }
    if (mine === run) set({ state: "error", error: "failed" });
  }
}

async function speakBrowser(chunks: string[], lang: Lang, mine: number): Promise<void> {
  const synth = window.speechSynthesis;
  const voice = pickVoice(await loadVoices(), lang);
  // Chrome pauses long queues silently; nudging resume() keeps it going.
  keepAlive = window.setInterval(() => synth.speaking && !synth.paused && synth.resume(), 10_000);
  try {
    for (const chunk of chunks) {
      if (mine !== run) return;
      await new Promise<void>((resolve, reject) => {
        const u = new SpeechSynthesisUtterance(chunk);
        u.lang = LOCALES[lang];
        try {
          if (voice) u.voice = voice;
        } catch {
          /* some engines reject a voice object; u.lang still selects the language */
        }
        u.rate = 0.98;
        u.onstart = () => mine === run && set({ state: "speaking" });
        u.onend = () => resolve();
        u.onerror = (e) => (e.error === "interrupted" || e.error === "canceled" ? resolve() : reject(new Error(e.error)));
        synth.speak(u);
      });
    }
  } finally {
    window.clearInterval(keepAlive);
  }
}

async function speakServer(chunks: string[], lang: Lang, mine: number): Promise<void> {
  // Fetch the next chunk while the current one plays.
  abort = new AbortController();
  const signal = abort.signal;
  let next: Promise<Blob> | null = api.tts(chunks[0], lang, signal);
  for (let i = 0; i < chunks.length; i++) {
    const blob = await next!;
    next = i + 1 < chunks.length ? api.tts(chunks[i + 1], lang, signal) : null;
    if (mine !== run) return;
    const url = URL.createObjectURL(blob);
    try {
      await new Promise<void>((resolve, reject) => {
        const a = new Audio(url);
        audio = a;
        a.onplaying = () => mine === run && set({ state: "speaking" });
        a.onended = () => resolve();
        a.onerror = () => reject(new Error("audio"));
        a.onpause = () => mine !== run && resolve();
        a.play().catch(reject);
      });
    } finally {
      URL.revokeObjectURL(url);
    }
  }
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useTts(): Snapshot {
  return useSyncExternalStore(subscribe, () => snap, () => snap);
}
