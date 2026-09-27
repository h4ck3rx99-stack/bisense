// Small UI primitives shared by every screen. Styling comes only from the design tokens in styles/index.css.
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, FlaskConical, RefreshCw, SearchX } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-strong border border-accent-strong",
  secondary: "bg-surface text-ink border border-line-strong hover:bg-surface-2",
  ghost: "bg-transparent text-ink-2 border border-transparent hover:bg-surface-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }>(
  function Button({ variant = "secondary", size = "md", className = "", ...rest }, ref) {
    const sz = size === "sm" ? "h-8 px-2.5 text-sm gap-1.5" : "h-10 px-3.5 text-[14px] gap-2";
    return (
      <button
        ref={ref}
        className={`inline-flex items-center justify-center rounded-md font-medium transition-colors duration-150 disabled:opacity-50 ${sz} ${variants[variant]} ${className}`}
        {...rest}
      />
    );
  },
);

export function Badge({ children, tone = "neutral", className = "", title }: { children: ReactNode; tone?: "neutral" | "accent" | "ok" | "warn" | "err" | "synth" | "calm" | "interp"; className?: string; title?: string }) {
  const tones = {
    neutral: "bg-surface-2 text-ink-2 border-line",
    accent: "bg-accent-soft text-accent-strong border-[#d6d3f3]",
    ok: "bg-ok-bg text-ok-ink border-[#c6e6d0]",
    warn: "bg-warn-bg text-warn-ink border-[#f0d9a8]",
    err: "bg-err-bg text-err-ink border-[#f2c9c9]",
    synth: "bg-synth-bg text-synth-ink border-synth-line border-dashed",
    calm: "bg-calm-bg text-calm-ink border-calm-line",
    interp: "bg-interp-bg text-interp-ink border-interp-line",
  } as const;
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-sm border px-1.5 py-px text-xs font-medium leading-5 ${tones[tone]} ${className}`}>
      {children}
    </span>
  );
}

export function SyntheticBadge({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <Badge tone="synth" title={t("synthetic.tooltip")}>
      <FlaskConical size={12} aria-hidden />
      {compact ? t("synthetic.short") : t("synthetic.badge")}
    </Badge>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

export function EmptyState({ title, body, action, icon }: { title: string; body?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="card flex flex-col items-start gap-2 p-6">
      <div className="text-ink-3">{icon ?? <SearchX size={20} aria-hidden />}</div>
      <h2 className="text-lg font-semibold">{title}</h2>
      {body && <div className="max-w-prose text-ink-2">{body}</div>}
      {action}
    </div>
  );
}

export function ErrorState({ messageKey, onRetry }: { messageKey: string; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-[#f2c9c9] bg-err-bg p-5 text-err-ink">
      <div className="flex items-center gap-2 font-semibold">
        <AlertTriangle size={18} aria-hidden />
        {t("error.title")}
      </div>
      <p className="text-ink-2">{t(messageKey, { defaultValue: t("error.internal") })}</p>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          <RefreshCw size={14} aria-hidden />
          {t("action.retry")}
        </Button>
      )}
    </div>
  );
}

export function SectionTitle({ children, id, right }: { children: ReactNode; id?: string; right?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-3">
      <h2 id={id} className="text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">
        {children}
      </h2>
      {right}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="mono rounded-sm border border-line-strong bg-surface-2 px-1 text-[11px] text-ink-2">{children}</kbd>;
}
