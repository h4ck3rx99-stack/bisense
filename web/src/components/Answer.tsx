// Answer rendering. The visual contract:
//   - "From the sources": source facts, each with citation chips and (when present) the verbatim quote;
//   - "AI interpretation": amber cards with their own icon + label, always citing what they interpret;
//   - honest states (insufficient evidence, clarification, extractive fallback, cached, partial) are distinct.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import * as Tooltip from "@radix-ui/react-tooltip";
import { BookOpenCheck, Check, CircleHelp, Copy, Info, Lightbulb, ListChecks, Quote, Scale, Sparkles, Volume2, VolumeX, X } from "lucide-react";
import type { Answer, Citation, Point, QueryInfo, StandardRef } from "../api/types";
import { Badge, SectionTitle, SyntheticBadge } from "./ui";
import { CitationChip, WithCitations } from "./Evidence";
import { useToast } from "./Toast";
import { shortTitle } from "../lib/format";
import { speak, stopSpeaking, ttsSupported, voiceFor } from "../lib/speech";
import { langInfo } from "../i18n/languages";
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

function PointText({ p, citations }: { p: Point; citations: Map<string, Citation> }) {
  return (
    <>
      <WithCitations text={p.text} citations={citations} />
      {p.citations.map((id) => (
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

function FactList({ points, citations, original }: { points: Point[]; citations: Map<string, Citation>; original?: Point[] }) {
  const { t } = useTranslation();
  const [showTr, setShowTr] = useState<Record<number, boolean>>({});
  return (
    <ul className="space-y-2.5">
      {points.map((p, i) => (
        <li key={i} className="border-l-[3px] border-fact-rule bg-surface py-1 pl-3">
          <p className="leading-relaxed">
            <PointText p={p} citations={citations} />
          </p>
          {p.quote && !quoteRepeatsText(p.quote, p.text) && (
            <blockquote className="mt-1.5 flex gap-2 rounded-md bg-surface-2 px-2.5 py-1.5 text-[14px] text-ink-2" lang="en">
              <Quote size={14} className="mt-1 shrink-0 text-ink-3" aria-hidden />
              <span>
                <span className="sr-only">{t("answer.verbatim")}: </span>“{p.quote}”
              </span>
            </blockquote>
          )}
          {original?.[i] && original[i].text !== p.text && (
            <div className="mt-1">
              <button type="button" className="text-xs font-medium text-accent hover:underline" onClick={() => setShowTr((s) => ({ ...s, [i]: !s[i] }))}>
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
      ))}
    </ul>
  );
}

function InterpretationList({ points, citations }: { points: Point[]; citations: Map<string, Citation> }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-lg border border-interp-line bg-interp-bg p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold text-interp-ink">
        <Lightbulb size={15} className="text-interp-icon" aria-hidden />
        {t("answer.interpretationTitle")}
      </div>
      <ul className="space-y-2">
        {points.map((p, i) => (
          <li key={i} className="leading-relaxed text-ink">
            <PointText p={p} citations={citations} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RelevantStandards({ standards, citations }: { standards: StandardRef[]; citations: Map<string, Citation> }) {
  const { t } = useTranslation();
  if (!standards.length) return null;
  return (
    <section aria-labelledby="rel-std">
      <SectionTitle id="rel-std">{t("answer.relevantStandards")}</SectionTitle>
      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
        {standards.map((s) => (
          <li key={s.slug} className="p-3">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <Link to={`/standards/${s.slug}`} className="mono text-[14px] font-semibold">
                {s.number ?? shortTitle(s.title, 60)}
              </Link>
              {s.synthetic && <SyntheticBadge compact />}
              {s.catalogue_only && <Badge tone="calm">{t("standard.catalogueOnlyShort")}</Badge>}
              <CompulsoryBadge status={s.compulsory} source={s.compulsory_source} />
            </div>
            {s.number && <div className="text-[13px] text-ink-2">{shortTitle(s.title, 110)}</div>}
            {s.why && (
              <p className="mt-1 text-[14px]">
                <WithCitations text={s.why} citations={citations} />
                {s.citations.map((id) => (
                  <CitationChip key={id} id={id} citations={citations} />
                ))}
              </p>
            )}
            {!s.why && s.matched_row && <p className="mt-1 text-[13px] text-ink-3">{t("answer.fromOfficialList")}: {s.matched_row}</p>}
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

function speakableText(a: Answer, t: (k: string) => string): string {
  const facts = a.points.filter((p) => p.kind === "source_fact").map((p) => p.text.replace(/\[C\d+\]/g, ""));
  return [a.summary.replace(/\[C\d+\]/g, ""), ...facts, t("answer.sourcesOnScreen")].filter(Boolean).join(". ");
}

export function AnswerBlock({ answer, citations, onFollowUp, onPickOption }: { answer: Answer; citations: Map<string, Citation>; onFollowUp?: (q: string) => void; onPickOption?: (q: string) => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [speaking, setSpeaking] = useState(false);
  const facts = answer.points.filter((p) => p.kind === "source_fact");
  const interps = answer.points.filter((p) => p.kind === "interpretation");
  const origFacts = answer.original?.points.filter((p) => p.kind === "source_fact");
  const locale = langInfo(answer.lang).speechLocale;
  const canSpeak = ttsSupported() && (answer.lang === "en" || voiceFor(locale) !== null);

  if (answer.answer_type === "insufficient_evidence") return <InsufficientEvidence answer={answer} />;
  if (answer.answer_type === "out_of_scope") {
    return (
      <div className="rounded-lg border border-calm-line bg-calm-bg p-4 text-calm-ink">
        <p className="font-medium">{t("answer.outOfScope")}</p>
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
            <button key={o} type="button" onClick={() => onPickOption?.(o)} className="h-9 rounded-md border border-line-strong bg-surface px-3 text-[13px] hover:border-accent">
              {o}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const copy = async () => {
    const lines = [answer.summary, ...answer.points.map((p) => `${p.kind === "interpretation" ? t("answer.interpretationShort") + ": " : ""}${p.text} ${p.citations.map((id) => `[${citations.get(id)?.n ?? id}]`).join("")}`)];
    const refs = [...new Set(answer.points.flatMap((p) => p.citations))].map((id) => citations.get(id)).filter(Boolean).map((c) => `[${c!.n}] ${c!.standard_number ?? c!.standard_title}, ${c!.clause_number}${c!.has_page_image ? `, p. ${c!.page_start}` : ""}`);
    try {
      await navigator.clipboard.writeText([...lines, "", ...refs].filter((x) => x !== undefined).join("\n"));
      toast(t("toast.copied"));
    } catch {
      toast(t("toast.copyFailed"), "warn");
    }
  };

  return (
    <div className="space-y-4">
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
            {t("answer.summaryTitle")}
          </SectionTitle>
          <p className="text-[16px] leading-relaxed">
            <WithCitations text={answer.summary} citations={citations} />
          </p>
        </section>
      )}

      {facts.length > 0 && (
        <section aria-labelledby="ans-facts">
          <SectionTitle id="ans-facts">{answer.mode === "extractive" ? t("answer.relevantClauses") : t("answer.fromSources")}</SectionTitle>
          <FactList points={facts} citations={citations} original={origFacts} />
        </section>
      )}

      {interps.length > 0 && <InterpretationList points={interps} citations={citations} />}

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

      {answer.dropped_count > 0 && <p className="text-xs text-ink-3">{t("answer.partial", { count: answer.dropped_count })}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <StrengthBadge answer={answer} />
        {answer.synthetic_used && <SyntheticBadge />}
        <span className="flex-1" />
        <button type="button" onClick={copy} className="inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium text-ink-2 hover:bg-surface-2">
          <Copy size={14} aria-hidden />
          {t("answer.copy")}
        </button>
        {canSpeak ? (
          <button
            type="button"
            onClick={() => {
              if (speaking) {
                stopSpeaking();
                setSpeaking(false);
              } else if (speak(speakableText(answer, t), locale, () => setSpeaking(false))) setSpeaking(true);
            }}
            className="inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium text-ink-2 hover:bg-surface-2"
            aria-pressed={speaking}
          >
            {speaking ? <VolumeX size={14} aria-hidden /> : <Volume2 size={14} aria-hidden />}
            {speaking ? t("answer.stopListening") : t("answer.listen")}
          </button>
        ) : (
          <span className="text-xs text-ink-3" title={t("answer.listenUnavailable")}>{t("answer.listenUnavailableShort")}</span>
        )}
      </div>

      {answer.follow_ups.length > 0 && onFollowUp && (
        <div className="flex flex-wrap gap-2" aria-label={t("answer.followUps")}>
          {answer.follow_ups.slice(0, 3).map((f) => (
            <button key={f} type="button" onClick={() => onFollowUp(f)} className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-line bg-surface px-3 py-1 text-left text-[13px] text-ink-2 hover:border-accent hover:text-accent-strong">
              <ListChecks size={13} aria-hidden />
              {f}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function InsufficientEvidence({ answer }: { answer: Answer }) {
  const { t } = useTranslation();
  const health = useHealth();
  const c = health.data?.counts ?? {};
  return (
    <div className="rounded-lg border border-calm-line bg-calm-bg p-4 text-calm-ink" role="status">
      <h3 className="mb-1 text-[16px] font-semibold">{t("insufficient.title")}</h3>
      <p className="mb-2 text-[14px]">{t("insufficient.body")}</p>
      {answer.gaps.length > 0 && (
        <ul className="mb-2 list-disc pl-5 text-[14px]">
          {answer.gaps.map((g, i) => (
            <li key={i}>{g}</li>
          ))}
        </ul>
      )}
      <p className="text-[13px]">{t("insufficient.searched", { std: c.standards_full_text ?? 0, guide: c.guidance ?? 0, cat: c.catalogue ?? 0 })}</p>
      <ul className="mt-2 list-disc pl-5 text-[13px]">
        <li>{t("insufficient.tip1")}</li>
        <li>{t("insufficient.tip2")}</li>
        <li>{t("insufficient.tip3")}</li>
      </ul>
    </div>
  );
}
