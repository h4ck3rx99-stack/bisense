// Answer rendering, in the order a beginner needs it:
//   1 Short answer  2 Key points (source facts; exact wording collapsed)  3 What this means for you (AI
//   interpretation, amber, own icon + label)  4 Relevant standards (plain title first)  5 Sources (human
//   citations; full evidence in the side panel)  6 Next steps (chips).
// Honest states (insufficient evidence, clarification, extractive fallback, cached, partial) are distinct.
import { useContext, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import * as Tooltip from "@radix-ui/react-tooltip";
import { ArrowRight, BookOpen, BookOpenCheck, Check, ChevronDown, CircleHelp, Columns2, Compass, Copy, FileText, Info, Languages, Lightbulb, ListChecks, Quote, Scale, SearchX, Sparkles, X } from "lucide-react";
import type { Answer, Citation, Lang, Point, QueryInfo, StandardRef } from "../api/types";
import { Badge, SectionTitle, SourceBadge, SyntheticBadge } from "./ui";
import { CitationActivateContext, CitationChip, WithCitations, focusEvidence } from "./Evidence";
import { useToast } from "./Toast";
import { humanSource, shortTitle } from "../lib/format";
import { ListenButton } from "./ListenButton";
import { useHealth } from "../lib/hooks";

const STAGES = ["understanding", "searching", "drafting", "verifying", "translating"] as const;

export function StageProgress({ stage, counts }: { stage: string | null; counts?: { sources?: number; passages?: number } }) {
  const { t } = useTranslation();
  const idx = stage ? STAGES.indexOf(stage as (typeof STAGES)[number]) : -1;
  return (
    <div className="card p-4" aria-live="polite" aria-atomic="true">
      <ol className="flex flex-wrap gap-x-4 gap-y-2 text-[13px]">
        {STAGES.filter((s) => s !== "translating" || stage === "translating").map((s, i) => {
          const state = i < idx ? "done" : i === idx ? "active" : "todo";
          return (
            <li key={s} className={`flex items-center gap-1.5 ${state === "todo" ? "text-ink-3" : "text-ink"}`}>
              <span className={`inline-flex h-4 w-4 items-center justify-center rounded-full border ${state === "done" ? "border-ok-ink bg-ok-bg text-ok-ink" : state === "active" ? "border-accent" : "border-line-strong"}`}>
                {state === "done" ? <Check size={11} aria-hidden /> : state === "active" ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> : null}
              </span>
              {t(`stage.${s}`, { n: counts?.sources ?? "", k: counts?.passages ?? "" })}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function StrengthBadge({ answer }: { answer: Answer }) {
  const { t } = useTranslation();
  if (answer.evidence_strength === "none") return null;
  const tone = answer.evidence_strength === "strong" ? "ok" : answer.evidence_strength === "moderate" ? "accent" : "warn";
  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button type="button" className="rounded-sm" aria-label={`${t(`strength.${answer.evidence_strength}`)}. ${answer.strength_basis}`}>
            <Badge tone={tone}>
              <BookOpenCheck size={12} aria-hidden />
              {t(`strength.${answer.evidence_strength}`)}
            </Badge>
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content sideOffset={6} className="z-50 max-w-xs rounded-md bg-ink px-3 py-2 text-xs leading-relaxed text-white shadow-[var(--shadow-pop)]">
            <div className="mb-0.5 font-semibold">{t("strength.tooltipTitle")}</div>
            {answer.strength_basis}
            <Tooltip.Arrow className="fill-ink" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

export function ScopeChip({ query, onClear }: { query: QueryInfo; onClear?: () => void }) {
  const { t } = useTranslation();
  if (!query.resolved_scope.length) return null;
  return (
    <div className="inline-flex max-w-full items-center gap-2 rounded-md border border-[#d6d3f3] bg-accent-soft py-1 pl-2.5 pr-1 text-[13px] text-accent-strong">
      <span className="shrink-0">{t(query.scope_source === "context" ? "scope.fromContext" : "scope.answeringAbout")}</span>
      <span className="mono truncate font-semibold">{query.resolved_scope.map((s) => s.number ?? shortTitle(s.title, 40)).join(", ")}</span>
      {onClear && (
        <button type="button" onClick={onClear} className="inline-flex h-7 items-center gap-1 rounded px-1.5 text-xs font-medium hover:bg-white" aria-label={t("scope.clear")}>
          <X size={13} aria-hidden />
          {t("scope.change")}
        </button>
      )}
    </div>
  );
}

/** Model text sometimes copies Markdown table cells ("Max | 275 g"); show them as readable separators. */
const tidy = (text: string) => text.replace(/\s\|\s/g, " · ");

/** Citation ids not already shown inline as [Cn] markers (avoids duplicate chips). */
const extraCitations = (text: string, ids: string[]) => ids.filter((id) => !text.includes(`[${id}]`));

function PointText({ p, citations }: { p: Point; citations: Map<string, Citation> }) {
  return (
    <>
      <WithCitations text={tidy(p.text)} citations={citations} />
      {extraCitations(p.text, p.citations).map((id) => (
        <CitationChip key={id} id={id} citations={citations} />
      ))}
    </>
  );
}

const normQ = (s: string) => s.toLowerCase().replace(/[“”"'.\s]+/g, " ").trim();

/** Hide a quote block when the statement above already says the same words verbatim. */
export function quoteRepeatsText(quote: string, text: string): boolean {
  const q = normQ(quote);
  const t = normQ(text);
  return t.includes(q) && q.length >= t.length * 0.6;
}

const MAX_KEY_POINTS = 5;

/** Key points (source facts). The exact source wording is collapsed under each point: beginners see a
 *  short statement, experts expand "Exact wording" to see the verbatim quote and where it comes from. */
function KeyPoints({ points, citations, original }: { points: Point[]; citations: Map<string, Citation>; original?: Point[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [showTr, setShowTr] = useState<Record<number, boolean>>({});
  const [all, setAll] = useState(false);
  const shown = all ? points : points.slice(0, MAX_KEY_POINTS);
  return (
    <>
      <ul className="space-y-2.5">
        {shown.map((p, i) => {
          const src = p.citations.map((id) => citations.get(id)).find(Boolean);
          const hasQuote = !!p.quote && !quoteRepeatsText(p.quote, p.text);
          return (
            <li key={i} className="border-l-[3px] border-fact-rule bg-surface py-1 pl-3">
              <p className="leading-relaxed">
                <PointText p={p} citations={citations} />
              </p>
              {(hasQuote || src) && (
                <button
                  type="button"
                  aria-expanded={!!open[i]}
                  onClick={() => setOpen((s) => ({ ...s, [i]: !s[i] }))}
                  className="mt-1 inline-flex min-h-8 items-center gap-1 rounded text-xs font-medium text-accent hover:underline"
                >
                  <ChevronDown size={13} className={`transition-transform ${open[i] ? "rotate-180" : ""}`} aria-hidden />
                  {open[i] ? t("answer.hideWording") : t("answer.showWording")}
                </button>
              )}
              {open[i] && (
                <div className="mt-1.5 rounded-md bg-surface-2 px-2.5 py-2 text-[14px] text-ink-2">
                  {hasQuote && (
                    <blockquote className="flex gap-2" lang="en">
                      <Quote size={14} className="mt-1 shrink-0 text-ink-3" aria-hidden />
                      <mark className="bg-transparent text-ink">
                        <span className="sr-only">{t("answer.verbatim")}: </span>“{p.quote}”
                      </mark>
                    </blockquote>
                  )}
                  {src && <p className="mt-1 text-xs text-ink-3">{humanSource(src, t)}</p>}
                </div>
              )}
              {original?.[i] && original[i].text !== p.text && (
                <div className="mt-1">
                  <button type="button" className="min-h-8 text-xs font-medium text-accent hover:underline" onClick={() => setShowTr((s) => ({ ...s, [i]: !s[i] }))}>
                    {showTr[i] ? t("answer.hideOriginal") : t("answer.showOriginal")}
                  </button>
                  {showTr[i] && (
                    <p className="mt-1 text-[13px] text-ink-3" lang="en">
                      {original[i].text}
                    </p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {points.length > MAX_KEY_POINTS && (
        <button type="button" onClick={() => setAll((v) => !v)} className="mt-2 min-h-9 text-[13px] font-medium text-accent hover:underline">
          {all ? t("answer.fewerPoints") : t("answer.morePoints", { count: points.length - MAX_KEY_POINTS })}
        </button>
      )}
    </>
  );
}

function InterpretationList({ points, citations }: { points: Point[]; citations: Map<string, Citation> }) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="ans-meaning" className="rounded-lg border border-interp-line bg-interp-bg p-3">
      <h3 id="ans-meaning" className="mb-0.5 flex items-center gap-1.5 text-[14px] font-semibold text-interp-ink">
        <Lightbulb size={15} className="text-interp-icon" aria-hidden />
        {t("answer.meaningTitle")}
      </h3>
      <p className="mb-2 text-xs text-interp-ink">{t("answer.meaningLabel")}</p>
      <ul className="space-y-2">
        {points.map((p, i) => (
          <li key={i} className="leading-relaxed text-ink">
            <PointText p={p} citations={citations} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** One compact card per standard: plain-language title first, number second, why it is relevant, Open. */
export function RelevantStandards({ standards, citations }: { standards: StandardRef[]; citations: Map<string, Citation> }) {
  const { t } = useTranslation();
  if (!standards.length) return null;
  return (
    <section aria-labelledby="rel-std">
      <SectionTitle id="rel-std">{t("answer.relevantStandards")}</SectionTitle>
      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
        {standards.map((s) => (
          <li key={s.slug} className="flex items-start gap-3 p-3">
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-medium leading-snug">{shortTitle(s.title, 110)}</div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                {s.number && <span className="mono text-[13px] text-ink-2">{s.number}</span>}
                {s.synthetic && <SyntheticBadge compact />}
                {s.catalogue_only && <Badge tone="calm">{t("standard.catalogueOnlyShort")}</Badge>}
                <CompulsoryBadge status={s.compulsory} source={s.compulsory_source} />
              </div>
              {s.why && (
                <p className="mt-1 text-[14px] text-ink-2">
                  <WithCitations text={tidy(s.why)} citations={citations} />
                  {extraCitations(s.why, s.citations).map((id) => (
                    <CitationChip key={id} id={id} citations={citations} />
                  ))}
                </p>
              )}
              {!s.why && s.matched_row && <p className="mt-1 text-[13px] text-ink-3">{t("answer.fromOfficialList")}: {s.matched_row}</p>}
            </div>
            <Link
              to={`/standards/${s.slug}`}
              className="inline-flex h-9 shrink-0 items-center gap-1 rounded-md border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink no-underline hover:border-accent"
              aria-label={t("answer.openStandard", { std: s.number ?? shortTitle(s.title, 60) })}
            >
              {t("answer.open")}
              <ArrowRight size={14} aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Human-readable list of the sources the answer actually cites. Tap -> the evidence card. */
function SourcesUsed({ answer, citations }: { answer: Answer; citations: Map<string, Citation> }) {
  const { t } = useTranslation();
  const ctxActivate = useContext(CitationActivateContext);
  const ids = [...new Set(answer.points.flatMap((p) => p.citations).concat(answer.standards.flatMap((s) => s.citations)))];
  const used = ids.map((id) => citations.get(id)).filter((c): c is Citation => !!c).sort((a, b) => a.n - b.n);
  if (!used.length) return null;
  return (
    <section aria-labelledby="ans-sources">
      <SectionTitle id="ans-sources">{t("answer.sourcesTitle")}</SectionTitle>
      <ul className="space-y-1.5">
        {used.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-2 text-[13px]">
            <button
              type="button"
              onClick={() => (ctxActivate ?? focusEvidence)(c.id)}
              className="mono inline-flex h-6 min-w-[24px] items-center justify-center rounded-sm border border-[#d6d3f3] bg-accent-soft px-1 text-[11px] font-semibold text-accent-strong hover:bg-accent hover:text-white"
              aria-label={t("answer.showSource", { n: c.n })}
            >
              {c.n}
            </button>
            <span className="min-w-0 flex-1 text-ink-2">{humanSource(c, t)}</span>
            {/* sample sources already say "Sample data, not official" in the label itself */}
            {c.source_type !== "sample" && !c.synthetic && <SourceBadge type={c.source_type} />}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function CompulsoryBadge({ status, source }: { status: string; source?: string | null }) {
  const { t } = useTranslation();
  if (status === "yes") return <Badge tone="warn" title={source ?? undefined}><Scale size={12} aria-hidden />{t("compulsory.yes")}</Badge>;
  if (status === "denotified") return <Badge tone="calm" title={source ?? undefined}>{t("compulsory.denotified")}</Badge>;
  return null;
}

/** What read-aloud says: the short answer and key points, then "Sources are shown on screen". */
export function speakableText(a: Answer, t: (k: string) => string): string {
  const clean = (s: string) => s.replace(/\[C\d+\]/g, "").replace(/https?:\/\/\S+/g, "").replace(/[*_#`>|]/g, " ").replace(/\s+/g, " ").trim();
  const facts = a.points.filter((p) => p.kind === "source_fact").slice(0, MAX_KEY_POINTS).map((p) => clean(p.text));
  return [clean(a.summary), ...facts, t("answer.sourcesOnScreen")].filter(Boolean).join(". ");
}

type NextStep = { key: string; label: string; icon: typeof ListChecks; run: () => void; lang?: string };

function NextSteps({ answer, onFollowUp, onAskIn }: { answer: Answer; onFollowUp?: (q: string) => void; onAskIn?: (lang: Lang) => void }) {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const top = answer.standards.find((s) => !s.catalogue_only);
  const name = top ? (top.number ?? shortTitle(top.title, 60)) : null;
  const steps: NextStep[] = [];
  if (top && name && onFollowUp) {
    steps.push({ key: "req", label: t("next.requirements"), icon: ListChecks, run: () => onFollowUp(t("next.requirementsQuery", { std: name })) });
    steps.push({ key: "simple", label: t("next.explain"), icon: Sparkles, run: () => onFollowUp(t("next.explainQuery", { std: name })) });
  }
  if (top) steps.push({ key: "compare", label: t("next.compare"), icon: Columns2, run: () => nav(`/compare?a=${top.slug}`) });
  for (const f of answer.follow_ups) if (onFollowUp && steps.length < 3) steps.push({ key: f, label: f, icon: ListChecks, run: () => onFollowUp(f) });
  const others = (["hi", "kn", "en"] as Lang[]).filter((l) => l !== i18n.language);
  if (!steps.length && !onAskIn) return null;
  return (
    <section aria-labelledby="ans-next">
      <SectionTitle id="ans-next">{t("next.title")}</SectionTitle>
      <div className="flex flex-wrap gap-2">
        {steps.slice(0, 3).map(({ key, label, icon: Icon, run }) => (
          <button key={key} type="button" onClick={run} className="inline-flex min-h-10 items-center gap-1.5 rounded-md border border-line bg-surface px-3 py-1 text-left text-[13px] text-ink-2 hover:border-accent hover:text-accent-strong">
            <Icon size={14} aria-hidden />
            {label}
          </button>
        ))}
        {onAskIn &&
          others.slice(0, 2).map((l) => (
            <button key={l} type="button" lang={l} onClick={() => onAskIn(l)} className="inline-flex min-h-10 items-center gap-1.5 rounded-md border border-line bg-surface px-3 py-1 text-[13px] text-ink-2 hover:border-accent hover:text-accent-strong">
              <Languages size={14} aria-hidden />
              {t(l === "hi" ? "next.askInHi" : l === "kn" ? "next.askInKn" : "next.askInEn")}
            </button>
          ))}
      </div>
    </section>
  );
}

export function AnswerBlock({
  answer,
  citations,
  onFollowUp,
  onPickOption,
  onAskIn,
}: {
  answer: Answer;
  citations: Map<string, Citation>;
  onFollowUp?: (q: string) => void;
  onPickOption?: (q: string) => void;
  onAskIn?: (lang: Lang) => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const facts = answer.points.filter((p) => p.kind === "source_fact");
  const interps = answer.points.filter((p) => p.kind === "interpretation");
  const origFacts = answer.original?.points.filter((p) => p.kind === "source_fact");

  if (answer.answer_type === "insufficient_evidence") return <InsufficientEvidence answer={answer} />;
  if (answer.answer_type === "out_of_scope") {
    return (
      <div className="rounded-lg border border-calm-line bg-calm-bg p-4 text-calm-ink">
        <p className="font-medium">{t("answer.outOfScope")}</p>
        <InsufficientActions />
      </div>
    );
  }
  if (answer.answer_type === "clarification") {
    return (
      <div className="rounded-lg border border-[#d6d3f3] bg-accent-soft p-4">
        <p className="mb-2 flex items-center gap-2 font-medium text-accent-strong">
          <CircleHelp size={16} aria-hidden />
          {answer.clarifying_question === "clarify.product" ? t("clarify.product") : answer.clarifying_question}
        </p>
        <div className="flex flex-wrap gap-2">
          {answer.clarifying_options.map((o) => (
            <button key={o} type="button" onClick={() => onPickOption?.(o)} className="min-h-10 rounded-md border border-line-strong bg-surface px-3 text-[13px] hover:border-accent">
              {o}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const copy = async () => {
    const lines = [answer.summary, ...answer.points.map((p) => `${p.kind === "interpretation" ? t("answer.interpretationShort") + ": " : ""}${p.text} ${p.citations.map((id) => `[${citations.get(id)?.n ?? id}]`).join("")}`)];
    const refs = [...new Set(answer.points.flatMap((p) => p.citations))]
      .map((id) => citations.get(id))
      .filter((c): c is Citation => !!c)
      .map((c) => `[${c.n}] ${humanSource(c, t)}`);
    try {
      await navigator.clipboard.writeText([...lines, "", ...refs].filter((x) => x !== undefined).join("\n"));
      toast(t("toast.copied"));
    } catch {
      toast(t("toast.copyFailed"), "warn");
    }
  };

  return (
    <div className="space-y-5">
      {answer.mode === "extractive" && (
        <div className="flex items-start gap-2 rounded-lg border border-calm-line bg-calm-bg px-3 py-2.5 text-[14px] text-calm-ink">
          <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
          <div>
            <div className="font-medium">{t("answer.extractiveTitle")}</div>
            <div className="text-[13px]">{t(answer.notice === "notice.extractive_no_key" ? "answer.extractiveNoKey" : answer.notice === "notice.extractive_llm_declined" ? "answer.extractiveDeclined" : "answer.extractiveFailed")}</div>
          </div>
        </div>
      )}
      {answer.mode === "cached" && (
        <p className="text-xs text-ink-3">{t("answer.cachedNote", { date: answer.generated_at ? new Date(answer.generated_at).toLocaleString() : "" })}</p>
      )}
      {answer.translation_failed && <p className="rounded-md bg-warn-bg px-3 py-2 text-[13px] text-warn-ink">{t("answer.translationFailed")}</p>}

      {answer.summary && (
        <section aria-labelledby="ans-summary">
          <SectionTitle id="ans-summary" right={<Badge tone="neutral"><Sparkles size={11} aria-hidden />{t("answer.aiWritten")}</Badge>}>
            {t("answer.shortAnswer")}
          </SectionTitle>
          <p className="text-[17px] leading-relaxed">
            <WithCitations text={answer.summary} citations={citations} />
          </p>
        </section>
      )}

      {facts.length > 0 && (
        <section aria-labelledby="ans-facts">
          <SectionTitle id="ans-facts">
            <span className="inline-flex items-center gap-1.5">
              <FileText size={13} aria-hidden />
              {answer.mode === "extractive" ? t("answer.relevantClauses") : t("answer.keyPoints")}
            </span>
          </SectionTitle>
          <KeyPoints points={facts} citations={citations} original={origFacts} />
        </section>
      )}

      {interps.length > 0 && <InterpretationList points={interps} citations={citations} />}

      <RelevantStandards standards={answer.standards} citations={citations} />

      {answer.gaps.length > 0 && (
        <section aria-labelledby="ans-gaps" className="rounded-lg border border-calm-line bg-calm-bg p-3 text-[14px] text-calm-ink">
          <h3 id="ans-gaps" className="mb-1 font-semibold">{t("answer.gapsTitle")}</h3>
          <ul className="list-disc space-y-1 pl-5">
            {answer.gaps.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </section>
      )}

      <SourcesUsed answer={answer} citations={citations} />

      {answer.dropped_count > 0 && <p className="text-xs text-ink-3">{t("answer.partial", { count: answer.dropped_count })}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <StrengthBadge answer={answer} />
        {answer.synthetic_used && <SyntheticBadge />}
        <span className="flex-1" />
        <button type="button" onClick={copy} className="inline-flex h-10 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium text-ink-2 hover:bg-surface-2">
          <Copy size={14} aria-hidden />
          {t("answer.copy")}
        </button>
        <ListenButton id={`${answer.generated_at ?? ""}:${answer.summary.slice(0, 40)}`} text={speakableText(answer, t)} lang={answer.lang as Lang} />
      </div>

      <NextSteps answer={answer} onFollowUp={onFollowUp} onAskIn={onAskIn} />
    </div>
  );
}

function InsufficientActions() {
  const { t } = useTranslation();
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <Link to="/guide" className="inline-flex min-h-10 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink no-underline hover:border-accent">
        <Compass size={14} aria-hidden />
        {t("insufficient.tryGuide")}
      </Link>
      <Link to="/standards" className="inline-flex min-h-10 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink no-underline hover:border-accent">
        <BookOpen size={14} aria-hidden />
        {t("insufficient.browse")}
      </Link>
    </div>
  );
}

export function InsufficientEvidence({ answer }: { answer: Answer }) {
  const { t } = useTranslation();
  const health = useHealth();
  const c = health.data?.counts ?? {};
  return (
    <div className="rounded-lg border border-calm-line bg-calm-bg p-4 text-calm-ink" role="status">
      <h3 className="mb-1 flex items-center gap-2 text-[16px] font-semibold">
        <SearchX size={17} aria-hidden />
        {t("insufficient.title")}
      </h3>
      <p className="mb-2 text-[14px]">{t("insufficient.body")}</p>
      {answer.gaps.length > 0 && (
        <ul className="mb-2 list-disc pl-5 text-[14px]">
          {answer.gaps.map((g, i) => (
            <li key={i}>{g}</li>
          ))}
        </ul>
      )}
      <p className="text-[13px]">{t("insufficient.searched", { std: c.standards_full_text ?? 0, guide: c.guidance ?? 0, cat: c.catalogue ?? 0 })}</p>
      <p className="mt-2 text-[13px] font-medium">{t("insufficient.tryTitle")}</p>
      <ul className="mt-1 list-disc pl-5 text-[13px]">
        <li>{t("insufficient.tip1")}</li>
        <li>{t("insufficient.tip2")}</li>
        <li>{t("insufficient.tip3")}</li>
      </ul>
      <InsufficientActions />
    </div>
  );
}
