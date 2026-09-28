// Microphone recording for voice questions: MediaRecorder -> /api/voice/stt (server Whisper).
// The transcript is put in the question box for the user to check; nothing is asked automatically.
//
// States: idle -> requesting (permission prompt) -> recording -> transcribing -> idle (text) | error.
// Every browser failure is mapped to a message key the UI can explain in the user's language.

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type { Lang } from "../api/types";

export type RecState = "idle" | "requesting" | "recording" | "transcribing" | "error";

export type MicErrorCode =
  | "insecure" // page not on HTTPS/localhost: browsers block the microphone
  | "unsupported" // no getUserMedia / MediaRecorder
  | "denied" // user or policy blocked the microphone
  | "no_device" // no microphone found
  | "busy" // microphone in use by another app, or hardware error
  | "no_speech" // recording was silent, or the server heard nothing
  | "too_short"
  | "server" // server STT failed (code in detail)
  | "unavailable" // server STT not configured
  | "network";

export class MicError extends Error {
  constructor(
    public code: MicErrorCode,
    public detail = "",
  ) {
    super(code);
  }
}

/** Map a getUserMedia/MediaRecorder exception to a stable code. */
export function micErrorFrom(e: unknown): MicError {
  const name = (e as { name?: string } | null)?.name ?? "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "SecurityError") return new MicError("denied");
  if (name === "NotFoundError" || name === "DevicesNotFoundError" || name === "OverconstrainedError") return new MicError("no_device");
  if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError") return new MicError("busy");
  return new MicError("busy", name);
}

/** Map a server STT error code to a UI error. */
export function sttErrorFrom(e: unknown): MicError {
  if (e instanceof ApiError) {
    if (e.status === 0) return new MicError("network");
    if (e.code === "stt_unavailable") return new MicError("unavailable");
    if (e.code === "audio_empty") return new MicError("too_short");
    return new MicError("server", e.code);
  }
  return new MicError("server", String(e));
}

export function micSupport(): MicErrorCode | null {
  if (typeof window === "undefined") return "unsupported";
  if (!window.isSecureContext) return "insecure";
  if (!navigator.mediaDevices?.getUserMedia || typeof window.MediaRecorder === "undefined") return "unsupported";
  return null;
}

/** First container/codec this browser can record. Whisper accepts all of these. */
export function pickMimeType(): string {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4", "audio/mpeg"];
  for (const c of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported?.(c)) return c;
  }
  return "";
}

// Peak RMS (0..1) below this is treated as silence and never uploaded.
export const SILENCE_RMS = 0.012;
const MIN_MS = 600;

export interface VoiceResult {
  text: string;
  language: string | null;
}

export interface Recorder {
  state: RecState;
  level: number; // 0..1, smoothed input level for the meter
  elapsed: number; // seconds
  maxSeconds: number;
  error: MicError | null;
  start(): Promise<void>;
  stop(): void; // stop and transcribe
  cancel(): void; // stop and discard
}

export function useRecorder(lang: Lang, maxSeconds: number, onResult: (r: VoiceResult) => void): Recorder {
  const [state, setState] = useState<RecState>("idle");
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<MicError | null>(null);
  const r = useRef({
    stream: null as MediaStream | null,
    rec: null as MediaRecorder | null,
    ctx: null as AudioContext | null,
    raf: 0,
    timer: 0,
    chunks: [] as Blob[],
    peak: 0,
    startedAt: 0,
    discard: false,
    abort: null as AbortController | null,
    lang,
    onResult,
  });
  r.current.lang = lang;
  r.current.onResult = onResult;

  const release = useCallback(() => {
    const s = r.current;
    cancelAnimationFrame(s.raf);
    window.clearInterval(s.timer);
    s.stream?.getTracks().forEach((t) => t.stop());
    s.stream = null;
    if (s.ctx && s.ctx.state !== "closed") void s.ctx.close().catch(() => undefined);
    s.ctx = null;
    setLevel(0);
  }, []);

  const fail = useCallback(
    (e: MicError) => {
      release();
      setError(e);
      setState("error");
    },
    [release],
  );

  const transcribe = useCallback(
    async (blob: Blob, durationMs: number) => {
      const s = r.current;
      if (durationMs < MIN_MS) return fail(new MicError("too_short"));
      if (s.peak < SILENCE_RMS) return fail(new MicError("no_speech"));
      setState("transcribing");
      s.abort = new AbortController();
      try {
        const out = await api.stt(blob, s.lang, s.abort.signal);
        if (out.no_speech || !out.text.trim()) return fail(new MicError("no_speech"));
        setState("idle");
        s.onResult({ text: out.text, language: out.language ?? null });
      } catch (e) {
        if ((e as { name?: string }).name === "AbortError") return;
        fail(sttErrorFrom(e));
      } finally {
        s.abort = null;
      }
    },
    [fail],
  );

  const start = useCallback(async () => {
    const s = r.current;
    const unsupported = micSupport();
    if (unsupported) return fail(new MicError(unsupported));
    setError(null);
    setElapsed(0);
    setState("requesting");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
    } catch (e) {
      return fail(micErrorFrom(e));
    }
    s.stream = stream;
    s.chunks = [];
    s.peak = 0;
    s.discard = false;

    // Level meter (also tells us whether anything was said).
    try {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new Ctx();
      s.ctx = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const buf = new Float32Array(analyser.fftSize);
      let smooth = 0;
      const tick = () => {
        analyser.getFloatTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += v * v;
        const rms = Math.sqrt(sum / buf.length);
        s.peak = Math.max(s.peak, rms);
        smooth = smooth * 0.7 + Math.min(1, rms * 6) * 0.3;
        setLevel(smooth);
        s.raf = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      s.peak = 1; // no meter available: let the server decide whether there was speech
    }

    let rec: MediaRecorder;
    try {
      const mimeType = pickMimeType();
      rec = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    } catch (e) {
      return fail(micErrorFrom(e));
    }
    s.rec = rec;
    rec.ondataavailable = (ev) => {
      if (ev.data.size) s.chunks.push(ev.data);
    };
    rec.onerror = () => fail(new MicError("busy"));
    rec.onstop = () => {
      const duration = performance.now() - s.startedAt;
      const type = rec.mimeType || s.chunks[0]?.type || "audio/webm";
      const blob = new Blob(s.chunks, { type });
      release();
      s.rec = null;
      if (s.discard) {
        setState("idle");
        return;
      }
      void transcribe(blob, duration);
    };
    // A microphone unplugged mid-recording ends the track.
    stream.getAudioTracks()[0]?.addEventListener("ended", () => {
      if (s.rec?.state === "recording") s.rec.stop();
    });
    s.startedAt = performance.now();
    rec.start(250);
    setState("recording");
    s.timer = window.setInterval(() => {
      const sec = (performance.now() - s.startedAt) / 1000;
      setElapsed(Math.floor(sec));
      if (sec >= maxSeconds && s.rec?.state === "recording") s.rec.stop();
    }, 200);
  }, [fail, maxSeconds, release, transcribe]);

  const stop = useCallback(() => {
    const s = r.current;
    if (s.rec?.state === "recording") s.rec.stop();
  }, []);

  const cancel = useCallback(() => {
    const s = r.current;
    s.discard = true;
    s.abort?.abort();
    if (s.rec?.state === "recording") s.rec.stop();
    else release();
    setError(null);
    setState("idle");
  }, [release]);

  // Release the microphone when the component unmounts (route change) — never leave it on.
  useEffect(
    () => () => {
      const s = r.current;
      s.discard = true;
      s.abort?.abort();
      if (s.rec?.state === "recording") s.rec.stop();
      release();
    },
    [release],
  );

  return { state, level, elapsed, maxSeconds, error, start, stop, cancel };
}
