import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";

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
