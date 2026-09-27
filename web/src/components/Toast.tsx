// Small non-blocking notifications (copied, exported, rate-limited, provider fallback used).
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

interface Toast {
  id: number;
  text: string;
  tone: "info" | "warn";
}

const ToastCtx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const { t } = useTranslation();
  const push = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = nextId.current++;
    setToasts((ts) => [...ts.slice(-2), { id, text, tone }]);
    window.setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), 4000);
  }, []);
  const value = useMemo(() => push, [push]);
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4 sm:bottom-6">
        {toasts.map((x) => (
          <div
            key={x.id}
            className={`pointer-events-auto flex max-w-md items-center gap-3 rounded-md px-3.5 py-2.5 text-sm shadow-[var(--shadow-pop)] ${x.tone === "warn" ? "bg-warn-bg text-warn-ink border border-[#f0d9a8]" : "bg-ink text-white"}`}
          >
            <span>{x.text}</span>
            <button className="rounded p-0.5 opacity-80 hover:opacity-100" aria-label={t("action.dismiss")} onClick={() => setToasts((ts) => ts.filter((y) => y.id !== x.id))}>
              <X size={14} aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
