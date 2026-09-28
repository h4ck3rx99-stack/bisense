import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { api } from "../api/client";
import { setServerTtsLanguages, stopSpeaking } from "./tts";

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 30_000, retry: 1 });
}

export function useLibrary() {
  return useQuery({ queryKey: ["library"], queryFn: api.library, staleTime: 60_000 });
}

export function useOnline(): boolean {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

export function useDebounced<T>(value: T, ms = 150): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** One language context: changing page or language stops read-aloud; the server's voice languages are
 * registered once. (Recording is cancelled by the search box itself on language change or unmount.) */
export function useSpeechLifecycle(): void {
  const { pathname } = useLocation();
  const { i18n } = useTranslation();
  const voice = useQuery({ queryKey: ["voice-status"], queryFn: api.voiceStatus, staleTime: 5 * 60_000, retry: 1 });
  useEffect(() => {
    setServerTtsLanguages(voice.data?.tts_languages ?? []);
  }, [voice.data]);
  useEffect(() => stopSpeaking(), [pathname, i18n.language]);
  useEffect(() => {
    document.documentElement.lang = i18n.language;
  }, [i18n.language]);
}
