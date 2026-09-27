// Single language registry for the UI. Adding a language = one entry here + one <code>.json strings file
// (+ a server entry in server/bisense/i18n/languages.py).
import type { Lang } from "../api/types";

export interface LanguageInfo {
  code: Lang;
  label: string; // shown in the switcher
  name: string; // native name
  script: "Latin" | "Devanagari" | "Kannada";
  speechLocale: string; // BCP-47 for browser STT/TTS
}

export const LANGUAGES: LanguageInfo[] = [
  { code: "en", label: "EN", name: "English", script: "Latin", speechLocale: "en-IN" },
  { code: "hi", label: "हिं", name: "हिन्दी", script: "Devanagari", speechLocale: "hi-IN" },
  { code: "kn", label: "ಕನ್ನಡ", name: "ಕನ್ನಡ", script: "Kannada", speechLocale: "kn-IN" },
];

export const langInfo = (code: string): LanguageInfo => LANGUAGES.find((l) => l.code === code) ?? LANGUAGES[0];

export function detectScript(text: string): Lang | null {
  if (/[ऀ-ॿ]/.test(text)) return "hi";
  if (/[ಀ-೿]/.test(text)) return "kn";
  return null;
}
