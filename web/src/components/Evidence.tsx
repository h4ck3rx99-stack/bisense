// Evidence UI: citation chips [n], evidence cards and the evidence panel.
// Hover or focus a chip -> popover with snippet, clause and page. Click -> scroll to and flash the card.
import * as Popover from "@radix-ui/react-popover";
import { createContext, useContext, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ExternalLink, FileText, Image as ImageIcon, Languages } from "lucide-react";
import type { Citation, Lang } from "../api/types";
import { api } from "../api/client";
import { Badge, SourceBadge } from "./ui";
import { Highlighted, Markdown } from "./Markdown";
import { clauseLink, humanSource, isWebPage, shortTitle, sourceLabel } from "../lib/format";
import { PagePreviewDialog } from "./PagePreview";

/** Lets a page decide what a citation click does (e.g. switch to the Evidence tab first). */
export const CitationActivateContext = createContext<((id: string) => void) | null>(null);

export function focusEvidence(id: string) {
  const el = document.getElementById(`evidence-${id}`);
  if (!el) return;
  el.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  el.classList.remove("flash");
  void el.offsetWidth; // restart animation
  el.classList.add("flash");
  (el.querySelector("a,button") as HTMLElement | null)?.focus({ preventScroll: true });
}

export function PageLabel({ c }: { c: Pick<Citation, "page_start" | "page_end" | "doc_type" | "has_page_image"> }) {
  const { t } = useTranslation();
  if (isWebPage(c)) return <>{t("evidence.webPage")}</>;
  return <>{c.page_start === c.page_end ? t("evidence.page", { n: c.page_start }) : t("evidence.pages", { a: c.page_start, b: c.page_end })}</>;
}

export function CitationChip({ id, citations, onActivate }: { id: string; citations: Map<string, Citation>; onActivate?: (id: string) => void }) {
  const { t } = useTranslation();
  const ctxActivate = useContext(CitationActivateContext);
  const c = citations.get(id);
  const [open, setOpen] = useState(false);
  if (!c) return null;
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="mono mx-0.5 inline-flex h-[18px] min-w-[20px] -translate-y-px items-center justify-center rounded-sm border border-[#d6d3f3] bg-accent-soft px-1 align-baseline text-[11px] font-semibold text-accent-strong hover:bg-accent hover:text-white"
          aria-label={t("evidence.citationLabel", { n: c.n, source: sourceLabel(c), clause: c.clause_number })}
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onClick={(e) => {
            e.preventDefault();
            setOpen(false);
            (onActivate ?? ctxActivate ?? focusEvidence)(id);
          }}
        >
          {c.n}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="start"
          sideOffset={6}
          onOpenAutoFocus={(e) => e.preventDefault()}
          className="z-50 w-[min(92vw,380px)] rounded-lg border border-line bg-surface p-3 text-sm shadow-[var(--shadow-pop)]"
        >
          <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-2">
            <span className="font-medium">{humanSource(c, t)}</span>
            {!c.synthetic && c.source_type !== "sample" && <SourceBadge type={c.source_type} />}
          </div>
          {c.clause_heading && <div className="mb-1 font-medium">{c.clause_heading}</div>}
          <p className="line-clamp-6 whitespace-pre-line text-ink-2">{c.snippet.replace(/\|/g, " ").replace(/-{3,}/g, "")}</p>
          <Popover.Arrow className="fill-surface" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** Render text containing [C1] markers as text + citation chips. */
export function WithCitations({ text, citations }: { text: string; citations: Map<string, Citation> }) {
  const parts = text.split(/(\[C\d{1,2}\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[(C\d{1,2})\]$/);
        if (m) return citations.has(m[1]) ? <CitationChip key={i} id={m[1]} citations={citations} /> : null;
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

/** "Show translation" under a quoted passage in a Hindi/Kannada UI. The original stays on screen and is
 *  the authority; the translation is labelled as machine translation. */
function PassageTranslation({ text }: { text: string }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const [state, setState] = useState<"idle" | "loading" | "done" | "unavailable">("idle");
  const [out, setOut] = useState("");
  if (lang === "en") return null;
  const load = async () => {
    setState("loading");
    try {
      const r = await api.translate([text], lang);
      if (r.available && r.translations[0]) {
        setOut(r.translations[0]);
        setState("done");
      } else setState("unavailable");
    } catch {
      setState("unavailable");
    }
  };
  if (state === "done")
    return (
      <div className="mt-2 rounded-md bg-surface-2 px-2.5 py-2 text-[14px]" lang={lang}>
        <div className="mb-0.5 text-xs font-medium text-ink-3">{t("evidence.machineTranslation")}</div>
        <p className="whitespace-pre-line text-ink-2">{out}</p>
      </div>
    );
  if (state === "unavailable") return <p className="mt-2 text-xs text-ink-3">{t("evidence.translationUnavailable")}</p>;
  return (
    <button type="button" onClick={load} disabled={state === "loading"} aria-busy={state === "loading"} className="mt-1 inline-flex min-h-8 items-center gap-1 text-xs font-medium text-accent hover:underline disabled:opacity-60">
      <Languages size={13} aria-hidden />
      {state === "loading" ? t("evidence.translating") : t("evidence.showTranslation")}
    </button>
  );
}

export function EvidenceCard({ c, quote, cited, actions }: { c: Citation; quote?: string | null; cited?: boolean; actions?: ReactNode }) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState(false);
  const isTable = c.snippet.trimStart().startsWith("|") || c.snippet.includes("\n|");
  return (
    <article
      id={`evidence-${c.id}`}
      className={`card relative scroll-mt-24 p-3.5 ${c.synthetic ? "synthetic-stripes" : ""} ${cited ? "border-l-[3px] border-l-fact-rule" : ""}`}
      aria-label={t("evidence.cardLabel", { n: c.n, source: sourceLabel(c) })}
    >
      <header className="mb-1.5 flex items-start gap-2">
        <span className="mono mt-0.5 inline-flex h-5 min-w-[22px] items-center justify-center rounded-sm bg-ink px-1 text-[11px] font-semibold text-white">{c.n}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[13px] font-semibold text-ink">{humanSource(c, t)}</span>
            {!c.synthetic && c.source_type !== "sample" && <SourceBadge type={c.source_type} />}
            {c.standard_kind !== "standard" && <Badge>{t(`kind.${c.standard_kind}`)}</Badge>}
          </div>
          {c.clause_heading && <div className="mt-0.5 text-[13px] text-ink-2">{c.clause_heading}</div>}
          {c.standard_number && <div className="truncate text-xs text-ink-3" title={c.standard_title}>{shortTitle(c.standard_title, 80)}</div>}
        </div>
      </header>
      <div className="text-[14px] leading-relaxed text-ink">
        {isTable ? <Markdown text={c.snippet} /> : <p className="whitespace-pre-line" lang="en"><Highlighted text={c.snippet} phrase={quote} /></p>}
        {!isTable && <PassageTranslation text={c.snippet} />}
      </div>
      <footer className="mt-2 flex flex-wrap items-center gap-1">
        <Link to={clauseLink(c.slug, c.clause_number)} className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-[13px] font-medium hover:bg-surface-2">
          <FileText size={14} aria-hidden />
          {t("evidence.openClause")}
        </Link>
        {c.has_page_image && (
          <button type="button" onClick={() => setPreview(true)} className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-[13px] font-medium text-accent hover:bg-surface-2">
            <ImageIcon size={14} aria-hidden />
            {t("evidence.viewPage")}
          </button>
        )}
        {c.url && (
          <a href={c.url} target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-[13px] font-medium hover:bg-surface-2">
            <ExternalLink size={14} aria-hidden />
            {t("evidence.officialSource")}
          </a>
        )}
        {!c.url && !c.synthetic && <span className="px-2 text-xs text-ink-3">{t("evidence.noLink")}</span>}
        {actions}
      </footer>
      {preview && <PagePreviewDialog c={c} quote={quote ?? c.snippet.slice(0, 80)} onClose={() => setPreview(false)} />}
    </article>
  );
}
