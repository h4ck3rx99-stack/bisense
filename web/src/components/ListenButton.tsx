// "Listen" for an answer: loading -> speaking -> stopped, with an honest message when this device has no
// voice for the answer's language. Speech failures never touch the answer text.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Volume2, VolumeX } from "lucide-react";
import type { Lang } from "../api/types";
import { browserTtsSupported, engineFor, speakText, stopSpeaking, useTts, type TtsEngine } from "../lib/tts";
import { langInfo } from "../i18n/languages";

export function ListenButton({ id, text, lang }: { id: string; text: string; lang: Lang }) {
  const { t } = useTranslation();
  const tts = useTts();
  const [engine, setEngine] = useState<TtsEngine | null>(null);

  useEffect(() => {
    let live = true;
    void engineFor(lang).then((e) => live && setEngine(e));
    return () => {
      live = false;
    };
  }, [lang]);

  const mine = tts.id === id;
  const busy = mine && tts.state === "loading";
  const playing = mine && tts.state === "speaking";
  const failed = mine && tts.state === "error";

  if (engine === null) return null;
  if (engine === "none") {
    const msg = browserTtsSupported() ? t("tts.noVoice", { lang: langInfo(lang).name }) : t("tts.unsupported");
    return (
      <span className="text-xs text-ink-3" data-testid="tts-unavailable">
        {msg}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={() => (mine && (busy || playing) ? stopSpeaking() : void speakText(id, text, lang))}
        className="inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium text-ink-2 hover:bg-surface-2"
        aria-pressed={playing}
        data-tts-state={mine ? tts.state : "idle"}
        data-testid="listen"
      >
        {busy ? <Loader2 size={14} className="animate-spin" aria-hidden /> : playing ? <VolumeX size={14} aria-hidden /> : <Volume2 size={14} aria-hidden />}
        {busy ? t("tts.loading") : playing ? t("tts.stop") : t("tts.listen")}
      </button>
      {failed && (
        <span className="text-xs text-err-ink" role="status">
          {tts.error === "unavailable_lang" ? t("tts.noVoice", { lang: langInfo(lang).name }) : t("tts.failed")}
        </span>
      )}
    </span>
  );
}
