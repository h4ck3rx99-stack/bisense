// Browser speech helpers (Web Speech API). Voice input uses exactly the same /api/ask pipeline as typing.
// Everything is feature-detected; when unsupported the UI explains why and typing keeps working.

// Minimal typings: SpeechRecognition is not in TypeScript's DOM lib.
interface SRAlternative { transcript: string }
interface SRResult { isFinal: boolean; 0: SRAlternative; length: number }
interface SREvent { resultIndex: number; results: ArrayLike<SRResult> }
interface SRErrorEvent { error: string }
export interface Recognizer {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: SREvent) => void) | null;
  onerror: ((e: SRErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type RecognizerCtor = new () => Recognizer;

function ctor(): RecognizerCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognizerCtor; webkitSpeechRecognition?: RecognizerCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export const sttSupported = (): boolean => typeof window !== "undefined" && ctor() !== null;

export function createRecognizer(locale: string): Recognizer | null {
  const C = ctor();
  if (!C) return null;
  const r = new C();
  r.lang = locale;
  r.interimResults = true;
  r.continuous = false;
  return r;
}

const NUMBER_WORDS: Record<string, string> = {
  zero: "0", oh: "0", one: "1", two: "2", three: "3", four: "4", five: "5", six: "6", seven: "7", eight: "8", nine: "9",
  ten: "10", eleven: "11", twelve: "12", thirteen: "13", fourteen: "14", fifteen: "15", sixteen: "16", seventeen: "17",
  eighteen: "18", nineteen: "19", twenty: "20", thirty: "30", forty: "40", fifty: "50", sixty: "60", seventy: "70", eighty: "80", ninety: "90",
};

/**
 * Normalise spoken standard numbers: "I S fourteen five four three" -> "IS 14543",
 * "IS 14 5 4 3" -> "IS 14543", "is one seven eight six" -> "IS 1786".
 * Only digits following an "IS"/"I S" token are joined, so ordinary numbers in a sentence are untouched.
 */
export function normalizeSpokenNumbers(text: string): string {
  const tokens = text.replace(/[.,]/g, " ").split(/\s+/).filter(Boolean);
  const out: string[] = [];
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    const isPrefix = /^is$/i.test(t) || (/^i$/i.test(t) && /^s$/i.test(tokens[i + 1] ?? ""));
    if (isPrefix) {
      let j = /^i$/i.test(t) ? i + 2 : i + 1;
      let digits = "";
      while (j < tokens.length) {
        const w = tokens[j].toLowerCase();
        if (/^\d+$/.test(w)) digits += w;
        else if (w in NUMBER_WORDS) digits += NUMBER_WORDS[w];
        else break;
        j++;
      }
      if (digits.length >= 2) {
        out.push(`IS ${digits}`);
        i = j - 1;
        continue;
      }
    }
    out.push(t);
  }
  return out.join(" ");
}

// ---- text to speech ------------------------------------------------------------------------------

export const ttsSupported = (): boolean => typeof window !== "undefined" && "speechSynthesis" in window;

export function voiceFor(locale: string): SpeechSynthesisVoice | null {
  if (!ttsSupported()) return null;
  const voices = window.speechSynthesis.getVoices();
  const base = locale.split("-")[0];
  return voices.find((v) => v.lang === locale) ?? voices.find((v) => v.lang.startsWith(base)) ?? null;
}

export function speak(text: string, locale: string, onEnd?: () => void): boolean {
  if (!ttsSupported()) return false;
  const voice = voiceFor(locale);
  if (!voice && !locale.startsWith("en")) return false;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = locale;
  if (voice) u.voice = voice;
  u.rate = 0.98;
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  window.speechSynthesis.speak(u);
  return true;
}

export function stopSpeaking(): void {
  if (ttsSupported()) window.speechSynthesis.cancel();
}
