// App shell: skip link, top bar, offline banner, page content, disclaimer footer.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, useNavigate } from "react-router-dom";
import * as Popover from "@radix-ui/react-popover";
import { Clock, Menu, WifiOff, X } from "lucide-react";
import { LANGUAGES } from "../i18n/languages";
import { useHealth, useOnline, useSpeechLifecycle } from "../lib/hooks";
import { clearRecentQuestions, recentQuestions } from "../lib/storage";
import { SyntheticBadge } from "./ui";

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  return (
    <div role="group" aria-label={t("nav.language")} className="inline-flex rounded-md border border-line bg-surface p-0.5">
      {LANGUAGES.map((l) => {
        const active = i18n.language === l.code;
        return (
          <button
            key={l.code}
            type="button"
            lang={l.code}
            onClick={() => void i18n.changeLanguage(l.code)}
            aria-pressed={active}
            aria-label={l.name}
            className={`h-8 min-w-9 rounded-[5px] px-2 text-[13px] font-medium transition-colors ${active ? "bg-ink text-white" : "text-ink-2 hover:bg-surface-2"}`}
          >
            {l.label}
          </button>
        );
      })}
    </div>
  );
}

function LibraryIndicator() {
  const { t } = useTranslation();
  const { data, isError } = useHealth();
  if (isError) return <span className="text-xs text-err-ink">{t("health.backendDown")}</span>;
  if (!data) return <span className="skeleton inline-block h-4 w-28" />;
  if (data.status === "no_index") return <span className="text-xs text-warn-ink">{t("health.noIndex")}</span>;
  const c = data.counts;
  return (
    <Link to="/standards" className="hidden text-xs text-ink-3 no-underline hover:text-ink lg:inline" title={t("health.libraryTitle", { std: c.standards_full_text, guide: c.guidance, cat: c.catalogue })}>
      <span className="mono font-semibold text-ink-2">{c.standards_full_text}</span> {t("health.fullText")} ·{" "}
      <span className="mono font-semibold text-ink-2">{c.guidance}</span> {t("health.guidance")} ·{" "}
      <span className="mono font-semibold text-ink-2">{c.catalogue}</span> {t("health.catalogue")}
    </Link>
  );
}

function RecentMenu() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [items, setItems] = useState(recentQuestions());
  return (
    <Popover.Root onOpenChange={(o) => o && setItems(recentQuestions())}>
      <Popover.Trigger className="inline-flex h-9 items-center gap-1.5 rounded-md px-2 text-[13px] font-medium text-ink-2 hover:bg-surface-2" aria-label={t("nav.recent")}>
        <Clock size={15} aria-hidden />
        <span className="hidden xl:inline">{t("nav.recent")}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={6} className="z-50 w-[min(92vw,340px)] rounded-lg border border-line bg-surface p-2 shadow-[var(--shadow-pop)]">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-ink-3">{t("nav.recentTitle")}</span>
            {items.length > 0 && (
              <button type="button" className="text-xs text-accent hover:underline" onClick={() => { clearRecentQuestions(); setItems([]); }}>
                {t("action.clear")}
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="px-2 py-3 text-[13px] text-ink-3">{t("nav.recentEmpty")}</p>
          ) : (
            <ul>
              {items.map((q) => (
                <li key={q.at}>
                  <Popover.Close asChild>
                    <button type="button" lang={q.lang} onClick={() => nav(`/ask?q=${encodeURIComponent(q.q)}&lang=${q.lang}`)} className="w-full rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-surface-2">
                      {q.q}
                    </button>
                  </Popover.Close>
                </li>
              ))}
            </ul>
          )}
          <p className="px-2 pt-1 text-[11px] text-ink-3">{t("nav.recentPrivacy")}</p>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

const NAV = [
  { to: "/", key: "nav.search", end: true },
  { to: "/standards", key: "nav.standards", end: false },
  { to: "/compare", key: "nav.compare", end: false },
  { to: "/about", key: "nav.about", end: false },
];

export function TopBar() {
  const { t } = useTranslation();
  const { data } = useHealth();
  const [open, setOpen] = useState(false);
  const linkCls = ({ isActive }: { isActive: boolean }) =>
    `inline-flex h-9 items-center rounded-md px-2.5 text-[14px] font-medium no-underline transition-colors ${isActive ? "bg-surface-2 text-ink" : "text-ink-2 hover:text-ink hover:bg-surface-2"}`;
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-[rgb(246_246_244/0.92)] backdrop-blur-sm no-print">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-3 px-4 sm:px-6">
        <Link to="/" className="flex items-baseline gap-2 text-ink no-underline" aria-label={t("brand.home")}>
          <span className="text-[19px] font-bold tracking-[-0.03em] [font-family:Inter,ui-sans-serif,sans-serif]" lang="en">
            BI<span className="text-accent">Sense</span>
          </span>
        </Link>
        <nav aria-label={t("nav.main")} className="ml-2 hidden items-center gap-0.5 md:flex">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={linkCls}>
              {t(n.key)}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          {data?.dataset_mode === "demo" && (
            <span className="hidden sm:inline-flex">
              <SyntheticBadge compact />
            </span>
          )}
          <LibraryIndicator />
          <RecentMenu />
          <LanguageSwitcher />
          <button type="button" className="inline-flex h-9 w-9 items-center justify-center rounded-md hover:bg-surface-2 md:hidden" aria-label={open ? t("action.close") : t("nav.menu")} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? <X size={18} aria-hidden /> : <Menu size={18} aria-hidden />}
          </button>
        </div>
      </div>
      {open && (
        <nav aria-label={t("nav.main")} className="border-t border-line bg-page px-4 py-2 md:hidden">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={linkCls} onClick={() => setOpen(false)}>
              {t(n.key)}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}

export function Footer() {
  const { t } = useTranslation();
  return (
    <footer className="mt-16 border-t border-line no-print">
      <div className="mx-auto max-w-[1400px] px-4 py-6 text-[13px] text-ink-3 sm:px-6">
        <p className="max-w-3xl">{t("footer.disclaimer")}</p>
        <p className="mt-1">{t("footer.notExhaustive")}</p>
      </div>
    </footer>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const online = useOnline();
  useSpeechLifecycle();
  return (
    <>
      <a href="#main" className="skip-link">
        {t("nav.skip")}
      </a>
      <TopBar />
      {!online && (
        <div role="status" className="flex items-center justify-center gap-2 bg-warn-bg px-4 py-2 text-[13px] text-warn-ink no-print">
          <WifiOff size={14} aria-hidden />
          {t("offline.banner")}
        </div>
      )}
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1400px] px-4 pb-8 pt-6 outline-none sm:px-6">
        {children}
      </main>
      <Footer />
    </>
  );
}
