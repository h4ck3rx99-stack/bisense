import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import hi from "./hi.json";
import kn from "./kn.json";
import { safeGet, safeSet } from "../lib/storage";

const saved = safeGet("bisense.lang");
const initial = saved === "hi" || saved === "kn" || saved === "en" ? saved : "en";

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi }, kn: { translation: kn } },
  lng: initial,
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React already escapes
  returnNull: false,
});

function syncHtmlLang(lng: string) {
  document.documentElement.lang = lng;
}
syncHtmlLang(initial);
i18n.on("languageChanged", (lng) => {
  syncHtmlLang(lng);
  safeSet("bisense.lang", lng);
});

export default i18n;
