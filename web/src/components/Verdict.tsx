// The verdict card: the first thing on every answer.
//   1 Big verdict line ("Yes — BIS certification is compulsory for …" / "Not compulsory, but a standard exists" /
//     the short answer for BIS service questions)
//   2 One standard chip -> the standard page
//   3 What you need to do: 2-3 steps for the scheme (Scheme-I ISI mark / Scheme-II CRS)
//   4 One source line with the official link
//   5 One "Show proof and details" button; everything else lives behind it.
// The verdict itself comes from the server (built from the official list row / manual, never from model text).
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, ExternalLink, Info } from "lucide-react";
import type { Answer, Citation, Lang } from "../api/types";
import { shortTitle } from "../lib/format";
import { ListenButton } from "./ListenButton";

const MANAK_ONLINE = "https://www.manakonline.in";
const CRS_PORTAL = "https://www.crsbis.in";

/** Readable first sentence of a passage-style point: drops the "Document — Section: " label. */
function plainLine(text: string, max = 240): string {
  const s = text.replace(/\[C\d+\]/g, "").replace(/\s+/g, " ").trim();
  const body = /^[^:]{8,160}:\s/.test(s) ? s.slice(s.indexOf(":") + 1).trim() : s;
  const first = body.split(/(?<=[.!?।])\s/)[0] ?? body;
  return first.length > max ? `${first.slice(0, max - 1).trimEnd()}…` : first;
}

function sourceText(c: Citation | undefined, label: string | undefined, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (!c) return label ?? "";
  if (c.clause_kind === "list") return t("verdict.srcList");
  if (c.text_scope === "product_manual") return c.has_page_image ? t("verdict.srcManual", { page: c.page_start }) : t("verdict.srcManualNoPage");
  return c.document_title ?? c.standard_title;
}

export function VerdictCard({
  answer,
  citations,
  proofOpen,
  onToggleProof,
  speakText,
}: {
  answer: Answer;
  citations: Map<string, Citation>;
  proofOpen: boolean;
  onToggleProof: () => void;
  speakText: string;
}) {
  const { t } = useTranslation();
  const v = answer.verdict;
  if (!v || v.kind === "not_found") return null;
  const product = v.product ?? (v.standard_title ? shortTitle(v.standard_title, 60) : "");
  const cite = v.source?.citation_id ? citations.get(v.source.citation_id) : undefined;
  const std = v.standard_number ?? "";

  let headline: string;
  if (v.kind === "compulsory") headline = t("verdict.compulsory", { product });
  else if (v.kind === "not_compulsory" || v.kind === "standard_only") headline = t("verdict.notCompulsory");
  else {
    const first = answer.points.find((p) => p.kind === "source_fact");
    headline = answer.summary ? plainLine(answer.summary, 320) : first ? plainLine(first.text) : "";
  }

  const steps: { text: string; link?: { href: string; label: string } }[] =
    v.kind === "compulsory" && v.scheme === "ISI"
      ? [{ text: t("verdict.isi1"), link: { href: MANAK_ONLINE, label: t("verdict.manakOnline") } }, { text: t("verdict.isi2", { std }) }, { text: t("verdict.isi3") }]
      : v.kind === "compulsory" && v.scheme === "CRS"
        ? [{ text: t("verdict.crs1", { std }) }, { text: t("verdict.crs2"), link: { href: CRS_PORTAL, label: t("verdict.crsPortal") } }, { text: t("verdict.crs3") }]
        : [];

  const tone = v.kind === "compulsory" ? "border-warn-ink/30 bg-warn-bg" : v.kind === "info" ? "border-line bg-surface" : "border-ok-ink/30 bg-ok-bg";
  const Icon = v.kind === "compulsory" ? AlertTriangle : v.kind === "info" ? Info : CheckCircle2;

  return (
    <section className={`rounded-xl border p-4 sm:p-5 ${tone}`} aria-labelledby="verdict-line" data-testid="verdict-card" data-verdict={v.kind}>
      {v.possible && (
        <p className="mb-2 inline-flex items-center gap-1.5 rounded-md bg-surface px-2 py-1 text-[12px] font-semibold text-warn-ink" data-testid="possible-match">
          <AlertTriangle size={13} aria-hidden />
          {t("verdict.possible")}
        </p>
      )}
      <div className="flex items-start gap-3">
        <Icon size={22} className="mt-0.5 shrink-0" aria-hidden />
        <h2 id="verdict-line" className="min-w-0 flex-1 text-[19px] font-semibold leading-snug sm:text-[21px]">
          {headline}
        </h2>
      </div>

      {(v.kind === "not_compulsory" || v.kind === "standard_only") && product && (
        <p className="mt-1.5 pl-[34px] text-[14px] text-ink-2">{t(v.kind === "not_compulsory" ? "verdict.denotifiedNote" : "verdict.notListedNote", { product })}</p>
      )}
      {v.kind === "compulsory" && v.order_short && <p className="mt-1.5 pl-[34px] text-[14px] text-ink-2">{t("verdict.requiredBy", { order: v.order_short })}</p>}

      {v.standard_slug && (
        <Link
          to={`/standards/${v.standard_slug}`}
          className="mt-3 ml-[34px] inline-flex max-w-[calc(100%-34px)] items-center gap-2 rounded-full border border-line-strong bg-surface px-3 py-1.5 text-[14px] font-medium text-ink no-underline hover:border-accent"
          aria-label={t("verdict.standardChip", { std: std || product })}
          data-testid="standard-chip"
        >
          <span className="mono shrink-0">{std}</span>
          {v.standard_title && <span className="truncate text-ink-2">· {shortTitle(v.standard_title, 44)}</span>}
          <ArrowRight size={14} className="shrink-0" aria-hidden />
        </Link>
      )}

      {steps.length > 0 && (
        <div className="mt-4 pl-[34px]">
          <h3 className="mb-1.5 text-[14px] font-semibold">{t("verdict.todo")}</h3>
          <ol className="space-y-1.5 text-[15px] leading-snug">
            {steps.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="mono mt-px inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface text-[12px] font-semibold">{i + 1}</span>
                <span className="min-w-0">
                  {s.text}{" "}
                  {s.link && (
                    <a href={s.link.href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 font-medium whitespace-nowrap">
                      {s.link.label}
                      <ExternalLink size={12} aria-hidden />
                    </a>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {v.source && (
        <p className="mt-4 pl-[34px] text-[13px] text-ink-2" data-testid="verdict-source">
          <span className="font-semibold">{t("verdict.source")}</span> {sourceText(cite, v.source.label, t)}
          {v.source.url && (
            <>
              {" · "}
              <a href={v.source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 whitespace-nowrap">
                {t("verdict.officialPage")}
                <ExternalLink size={12} aria-hidden />
              </a>
            </>
          )}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 pl-[34px]">
        <button
          type="button"
          onClick={onToggleProof}
          aria-expanded={proofOpen}
          className="inline-flex min-h-10 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 text-[14px] font-medium text-ink hover:border-accent"
          data-testid="toggle-proof"
        >
          <ChevronDown size={15} className={`transition-transform ${proofOpen ? "rotate-180" : ""}`} aria-hidden />
          {proofOpen ? t("verdict.hideProof") : t("verdict.showProof")}
        </button>
        <span className="flex-1" />
        <ListenButton id={`${answer.generated_at ?? ""}:${headline.slice(0, 40)}`} text={speakText || headline} lang={answer.lang as Lang} />
      </div>
    </section>
  );
}
