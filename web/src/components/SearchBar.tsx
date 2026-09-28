// The main question box: typed or spoken input, "/" to focus.
// Voice: the microphone recording is transcribed on the server (Whisper) in the selected language, and
// the transcript is placed IN the box so the user can check and edit it before asking (standard numbers
// are often misheard). Browsers without MediaRecorder fall back to the browser's own speech recognition.
import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Loader2, Mic, Square, X } from "lucide-react";
import { api } from "../api/client";
import type { Lang } from "../api/types";
import { createRecognizer, normalizeSpokenNumbers, sttSupported, type Recognizer } from "../lib/speech";
import { stopSpeaking } from "../lib/tts";
import { micSupport, useRecorder, type VoiceResult } from "../lib/recorder";
import { langInfo } from "../i18n/languages";
import { Kbd } from "./ui";

export interface SearchBarHandle {
  focus(): void;
  setValue(v: string): void;
}

interface Props {
  initial?: string;
  onSubmit: (q: string) => void;
  busy?: boolean;
  size?: "lg" | "md";
  placeholder?: string;
  autoFocus?: boolean;
  label?: string;
  slashShortcut?: boolean;
  chip?: ReactNode;
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export function useVoiceStatus() {
  return useQuery({ queryKey: ["voice-status"], queryFn: api.voiceStatus, staleTime: 5 * 60_000, retry: 1 });
}

export const SearchBar = forwardRef<SearchBarHandle, Props>(function SearchBar(
  { initial = "", onSubmit, busy = false, size = "lg", placeholder, autoFocus, label, slashShortcut = true, chip },
  ref,
) {
  const { t, i18n } = useTranslation();
  const lang = (["en", "hi", "kn"].includes(i18n.language) ? i18n.language : "en") as Lang;
  const [value, setValue] = useState(initial);
  const [listening, setListening] = useState(false); // browser speech recognition fallback
  const [interim, setInterim] = useState("");
  const [voiceMsg, setVoiceMsg] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recRef = useRef<Recognizer | null>(null);
  const status = useVoiceStatus();
  const serverStt = status.data?.stt_available === true && micSupport() === null;
  const browserStt = sttSupported();

  const onVoice = ({ text, language }: VoiceResult) => {
    const clean = lang === "en" ? normalizeSpokenNumbers(text) : text;
    setValue(clean);
    const other = language && language !== lang ? langInfo(language).name : null;
    setVoiceMsg(other ? t("voice.detectedOther", { lang: other }) : t("voice.checkTranscript"));
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(clean.length, clean.length);
      }
    });
  };
  const recorder = useRecorder(lang, status.data?.max_seconds ?? 60, onVoice);
  const recording = recorder.state === "recording" || recorder.state === "requesting";

  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus(), setValue }), []);
  useEffect(() => setValue(initial), [initial]);

  useEffect(() => {
    if (recorder.state === "error" && recorder.error) {
      const code = recorder.error.code;
      // Server STT missing or down: say so, and offer the browser's recognizer when there is one.
      const fallback = (code === "unavailable" || code === "server" || code === "network") && browserStt ? " " + t("voice.tryBrowser") : "";
      setVoiceMsg(t(`voice.err.${code}`) + fallback);
    }
  }, [recorder.state, recorder.error, browserStt, t]);

  // Changing language mid-recording would transcribe in the wrong language: cancel instead.
  const langRef = useRef(lang);
  const cancelRecording = recorder.cancel;
  useEffect(() => {
    if (langRef.current !== lang) {
      cancelRecording();
      recRef.current?.abort();
      setListening(false);
      setVoiceMsg(null);
    }
    langRef.current = lang;
  }, [lang, cancelRecording]);

  useEffect(() => {
    if (!slashShortcut) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA" && !(e.target as HTMLElement)?.isContentEditable) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [slashShortcut]);

  useEffect(() => () => recRef.current?.abort(), []);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const q = value.trim();
    if (!q || busy || recording || recorder.state === "transcribing") return;
    onSubmit(q.slice(0, 1000));
  };

  const startBrowserRecognition = () => {
    const rec = createRecognizer(langInfo(lang).speechLocale);
    if (!rec) {
      setVoiceMsg(t("voice.err.unsupported"));
      return;
    }
    recRef.current = rec;
    setVoiceMsg(null);
    setInterim("");
    let finalText = "";
    rec.onresult = (e) => {
      let live = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else live += r[0].transcript;
      }
      setInterim(live);
      if (finalText) setValue(lang === "en" ? normalizeSpokenNumbers(finalText.trim()) : finalText.trim());
    };
    rec.onerror = (e) => {
      setVoiceMsg(
        e.error === "not-allowed" || e.error === "service-not-allowed"
          ? t("voice.err.denied")
          : e.error === "no-speech"
            ? t("voice.err.no_speech")
            : e.error === "audio-capture"
              ? t("voice.err.no_device")
              : e.error === "network"
                ? t("voice.err.network")
                : e.error === "language-not-supported"
                  ? t("voice.err.langBrowser", { lang: langInfo(lang).name })
                  : t("voice.err.busy"),
      );
    };
    rec.onend = () => {
      setListening(false);
      setInterim("");
      if (finalText) {
        setVoiceMsg(t("voice.checkTranscript"));
        inputRef.current?.focus();
      }
    };
    try {
      rec.start();
      setListening(true);
    } catch {
      setVoiceMsg(t("voice.err.busy"));
    }
  };

  const toggleMic = () => {
    stopSpeaking(); // never record our own read-aloud
    if (listening) {
      recRef.current?.stop();
      return;
    }
    if (recorder.state === "recording") {
      recorder.stop();
      return;
    }
    if (recorder.state === "requesting" || recorder.state === "transcribing") return;
    setVoiceMsg(null);
    if (serverStt) {
      void recorder.start();
      return;
    }
    if (browserStt && window.isSecureContext) {
      startBrowserRecognition();
      return;
    }
    const why = micSupport();
    setVoiceMsg(t(`voice.err.${why ?? (status.isError ? "network" : "unavailable")}`));
  };

  const big = size === "lg";
  const active = recording || listening;
  const transcribing = recorder.state === "transcribing";
  return (
    <form onSubmit={submit} role="search" className="w-full">
      <label htmlFor="bisense-q" className="sr-only">
        {label ?? t("search.label")}
      </label>
      <div
        className={`flex items-end gap-2 rounded-lg border bg-surface shadow-[0_1px_0_rgb(20_20_30/0.04)] transition-colors focus-within:border-accent ${active ? "border-accent" : "border-line-strong"} ${big ? "p-2 pl-3.5" : "p-1.5 pl-3"}`}
      >
        {chip}
        <textarea
          id="bisense-q"
          ref={inputRef}
          value={listening && interim ? `${value}${value ? " " : ""}${interim}` : value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          maxLength={1000}
          autoFocus={autoFocus}
          placeholder={placeholder ?? t("search.placeholder")}
          className={`min-h-[44px] min-w-0 flex-1 resize-none bg-transparent py-2.5 outline-none ${big ? "text-[17px]" : "text-[15px]"}`}
          style={{ fieldSizing: "content", maxHeight: 160 } as React.CSSProperties}
        />
        <button
          type="button"
          onClick={toggleMic}
          disabled={transcribing || recorder.state === "requesting"}
          className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md border ${active ? "border-err-ink bg-err-bg text-err-ink" : "border-transparent text-ink-2 hover:bg-surface-2"} disabled:opacity-60`}
          aria-label={active ? t("voice.stop") : t("voice.start", { lang: langInfo(lang).name })}
          aria-pressed={active}
          data-voice-state={listening ? "browser" : recorder.state}
        >
          {transcribing ? (
            <Loader2 size={18} className="animate-spin" aria-hidden />
          ) : active ? (
            <Square size={16} fill="currentColor" aria-hidden />
          ) : (
            <Mic size={18} aria-hidden />
          )}
        </button>
        <button
          type="submit"
          disabled={busy || !value.trim() || active || transcribing}
          className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-md bg-accent px-3.5 text-[14px] font-medium text-white hover:bg-accent-strong disabled:opacity-50"
          aria-label={t("search.submit")}
        >
          {busy ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <ArrowRight size={16} aria-hidden />}
          <span className="hidden sm:inline">{t("search.submit")}</span>
        </button>
      </div>

      {(recording || transcribing) && (
        <div className="mt-2 flex flex-wrap items-center gap-3 rounded-md border border-line bg-surface-2 px-3 py-2 text-[13px]" role="status" data-testid="voice-panel">
          {recorder.state === "requesting" && <span>{t("voice.requesting")}</span>}
          {recorder.state === "recording" && (
            <>
              <span className="inline-flex items-center gap-1.5 font-medium text-err-ink">
                <span className="h-2 w-2 animate-pulse rounded-full bg-err-ink" aria-hidden />
                {t("voice.recording", { lang: langInfo(lang).name })}
              </span>
              <LevelMeter level={recorder.level} label={t("voice.level")} />
              <span className="tabular-nums text-ink-2">
                {fmt(recorder.elapsed)} / {fmt(recorder.maxSeconds)}
              </span>
              <span className="ml-auto flex gap-2">
                <button type="button" onClick={recorder.stop} className="rounded-md bg-accent px-3 py-1.5 font-medium text-white hover:bg-accent-strong">
                  {t("voice.done")}
                </button>
                <button type="button" onClick={recorder.cancel} className="inline-flex items-center gap-1 rounded-md border border-line-strong px-3 py-1.5 hover:bg-surface">
                  <X size={14} aria-hidden />
                  {t("voice.cancel")}
                </button>
              </span>
            </>
          )}
          {transcribing && (
            <>
              <span className="inline-flex items-center gap-1.5">
                <Loader2 size={14} className="animate-spin" aria-hidden />
                {t("voice.transcribing", { lang: langInfo(lang).name })}
              </span>
              <button type="button" onClick={recorder.cancel} className="ml-auto rounded-md border border-line-strong px-3 py-1.5 hover:bg-surface">
                {t("voice.cancel")}
              </button>
            </>
          )}
        </div>
      )}

      <div className="mt-1.5 flex min-h-5 flex-wrap items-center justify-between gap-2 text-xs text-ink-3" aria-live="polite">
        <span data-testid="voice-message">
          {listening ? (
            <span className="inline-flex items-center gap-1.5 text-err-ink">
              <span className="h-2 w-2 animate-pulse rounded-full bg-err-ink" aria-hidden />
              {t("voice.listening", { lang: langInfo(lang).name })}
            </span>
          ) : recording || transcribing ? null : (
            (voiceMsg ?? t("voice.hint", { lang: langInfo(lang).name }))
          )}
        </span>
        {big && slashShortcut && (
          <span className="hidden sm:inline">
            {t("search.pressSlash")} <Kbd>/</Kbd>
          </span>
        )}
      </div>
    </form>
  );
});

function LevelMeter({ level, label }: { level: number; label: string }) {
  const bars = 12;
  const lit = Math.round(level * bars);
  return (
    <span className="inline-flex h-4 items-end gap-[2px]" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(level * 100)} data-testid="voice-level">
      {Array.from({ length: bars }, (_, i) => (
        <span key={i} className={`w-[3px] rounded-sm ${i < lit ? "bg-accent" : "bg-line-strong"}`} style={{ height: `${30 + (i / bars) * 70}%` }} />
      ))}
    </span>
  );
}
