// The main question box: typed or spoken input, "/" to focus.
// Voice: the final transcript is placed IN the box so the user can check and edit it before asking
// (standard numbers are often misheard). Spoken numbers like "I S fourteen five four three" -> "IS 14543".
import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight, Loader2, Mic, Square } from "lucide-react";
import { createRecognizer, normalizeSpokenNumbers, sttSupported, type Recognizer } from "../lib/speech";
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

export const SearchBar = forwardRef<SearchBarHandle, Props>(function SearchBar(
  { initial = "", onSubmit, busy = false, size = "lg", placeholder, autoFocus, label, slashShortcut = true, chip },
  ref,
) {
  const { t, i18n } = useTranslation();
  const [value, setValue] = useState(initial);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [voiceMsg, setVoiceMsg] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recRef = useRef<Recognizer | null>(null);
  const supported = sttSupported();

  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus(), setValue }), []);
  useEffect(() => setValue(initial), [initial]);

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
    if (!q || busy) return;
    onSubmit(q.slice(0, 1000));
  };

  const toggleMic = () => {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const rec = createRecognizer(langInfo(i18n.language).speechLocale);
    if (!rec) {
      setVoiceMsg(t("voice.unsupported"));
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
      if (finalText) setValue(normalizeSpokenNumbers(finalText.trim()));
    };
    rec.onerror = (e) => {
      setVoiceMsg(e.error === "not-allowed" || e.error === "service-not-allowed" ? t("voice.denied") : e.error === "no-speech" ? t("voice.noSpeech") : t("voice.error"));
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
      setVoiceMsg(t("voice.error"));
    }
  };

  const big = size === "lg";
  return (
    <form onSubmit={submit} role="search" className="w-full">
      <label htmlFor="bisense-q" className="sr-only">
        {label ?? t("search.label")}
      </label>
      <div className={`flex items-end gap-2 rounded-lg border bg-surface shadow-[0_1px_0_rgb(20_20_30/0.04)] transition-colors focus-within:border-accent ${listening ? "border-accent" : "border-line-strong"} ${big ? "p-2 pl-3.5" : "p-1.5 pl-3"}`}>
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
        {supported && (
          <button
            type="button"
            onClick={toggleMic}
            className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md border ${listening ? "border-err-ink bg-err-bg text-err-ink" : "border-transparent text-ink-2 hover:bg-surface-2"}`}
            aria-label={listening ? t("voice.stop") : t("voice.start")}
            aria-pressed={listening}
          >
            {listening ? <Square size={16} fill="currentColor" aria-hidden /> : <Mic size={18} aria-hidden />}
          </button>
        )}
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-md bg-accent px-3.5 text-[14px] font-medium text-white hover:bg-accent-strong disabled:opacity-50"
          aria-label={t("search.submit")}
        >
          {busy ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <ArrowRight size={16} aria-hidden />}
          <span className="hidden sm:inline">{t("search.submit")}</span>
        </button>
      </div>
      <div className="mt-1.5 flex min-h-5 flex-wrap items-center justify-between gap-2 text-xs text-ink-3" aria-live="polite">
        <span>
          {listening ? (
            <span className="inline-flex items-center gap-1.5 text-err-ink">
              <span className="h-2 w-2 animate-pulse rounded-full bg-err-ink" aria-hidden />
              {t("voice.listening", { lang: langInfo(i18n.language).name })}
            </span>
          ) : (
            voiceMsg ?? (supported ? t("voice.hint") : t("voice.unsupportedShort"))
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
