// /ask — question answering with a follow-up thread.
// Order on screen: stage progress -> verdict card (answer) -> "Show proof and details" (evidence, key points,
// how it was found). One column until the proof is opened; on wide screens the evidence then opens beside
// the answer, on phones inside the details.
// Context sent to the server: the last 2 questions + the standards cited/focused in the last turn
// (+ the standard opened from the explorer). Previous AI answers are never sent back.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Layers } from "lucide-react";
import { ask } from "../api/sse";
import { ApiError } from "../api/client";
import type { Answer, AskContext, AskTrace, Citation, EvidenceEvent, Lang, QueryInfo } from "../api/types";
import { AnswerBlock, ScopeChip, StageProgress } from "../components/Answer";
import { CitationActivateContext, EvidenceCard, focusEvidence } from "../components/Evidence";
import { SearchBar, type SearchBarHandle } from "../components/SearchBar";
import { ErrorState, SectionTitle, Skeleton } from "../components/ui";
import { RetrievalDrawer } from "../components/RetrievalDrawer";
import { useToast } from "../components/Toast";
import { pushRecentQuestion } from "../lib/storage";
import { useMediaQuery } from "../lib/hooks";
import { detectScript } from "../i18n/languages";

interface Turn {
  id: number;
  query: string;
  lang: Lang;
  context?: AskContext;
  stage: string | null;
  stageDetail: { sources?: number; passages?: number };
  info: QueryInfo | null;
  evidence: EvidenceEvent | null;
  answer: Answer | null;
  trace: AskTrace | null;
  error: string | null;
  done: boolean;
}

let turnSeq = 1;

export default function Ask() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [focusId, setFocusId] = useState<number | null>(null);
  const [proofOpen, setProofOpen] = useState<Record<number, boolean>>({});
  const wide = useMediaQuery("(min-width: 1024px)");
  const started = useRef<string | null>(null);
  const aborters = useRef<AbortController[]>([]);
  const followRef = useRef<SearchBarHandle>(null);

  const update = useCallback((id: number, patch: Partial<Turn> | ((t: Turn) => Partial<Turn>)) => {
    setTurns((ts) => ts.map((x) => (x.id === id ? { ...x, ...(typeof patch === "function" ? patch(x) : patch) } : x)));
  }, []);

  const run = useCallback(
    (query: string, opts: { context?: AskContext; replace?: boolean; lang?: Lang } = {}) => {
      const lang: Lang = opts.lang ?? (detectScript(query) ?? (i18n.language as Lang));
      const turn: Turn = { id: turnSeq++, query, lang, context: opts.context, stage: "understanding", stageDetail: {}, info: null, evidence: null, answer: null, trace: null, error: null, done: false };
      setTurns((ts) => (opts.replace ? [turn] : [...ts, turn]));
      setFocusId(turn.id);
      pushRecentQuestion(query, lang);
      const ac = new AbortController();
      aborters.current.push(ac);
      ask(
        query,
        lang,
        opts.context,
        {
          onStage: (e) => update(turn.id, (x) => ({ stage: e.stage, stageDetail: { ...x.stageDetail, ...(e.detail as Turn["stageDetail"]) } })),
          onQuery: (e) => update(turn.id, { info: e }),
          onEvidence: (e) => update(turn.id, { evidence: e }),
          onAnswer: (e) => {
            update(turn.id, { answer: e });
            if (e.mode === "extractive" && e.notice === "notice.extractive_llm_failed") toast(t("toast.fallbackUsed"), "warn");
          },
          onTrace: (e) => update(turn.id, { trace: e }),
          onError: (e) => update(turn.id, { error: e.message_key, done: true }),
          onDone: () => update(turn.id, { done: true }),
        },
        ac.signal,
      ).catch((err: unknown) => {
        const key = err instanceof ApiError ? err.messageKey : "error.internal";
        if (err instanceof ApiError && err.status === 429) toast(t("toast.rateLimited"), "warn");
        update(turn.id, { error: key, done: true });
      });
    },
    [i18n.language, t, toast, update],
  );

  // Start from the URL (?q=&lang=&scope=)
  useEffect(() => {
    const q = params.get("q");
    if (!q) return;
    const key = `${q}|${params.get("scope") ?? ""}`;
    if (started.current === key) return;
    started.current = key;
    const scope = params.get("scope");
    const urlLang = params.get("lang");
    if (urlLang && urlLang !== i18n.language && ["en", "hi", "kn"].includes(urlLang)) void i18n.changeLanguage(urlLang);
    run(q, { replace: true, lang: (urlLang as Lang) ?? undefined, context: scope ? { open_slug: scope, focus_slugs: [scope], recent_questions: [] } : undefined });
  }, [params, run, i18n]);

  useEffect(() => () => aborters.current.forEach((a) => a.abort()), []);

  const last = turns[turns.length - 1];
  const focused = turns.find((x) => x.id === focusId) ?? last;

  const buildContext = (): AskContext => {
    const prev = turns.filter((x) => x.done);
    const recent = prev.slice(-2).map((x) => x.query);
    const l = prev[prev.length - 1];
    const cited = new Set<string>();
    if (l?.answer) {
      const byId = new Map((l.evidence?.citations ?? []).map((c) => [c.id, c]));
      // Official list sections are not documents one follows up on; never carry them as scope.
      l.answer.points.forEach((p) =>
        p.citations.forEach((id) => {
          const c = byId.get(id);
          if (c && c.clause_kind !== "list") cited.add(c.slug);
        }),
      );
      l.answer.standards.forEach((s) => s.kind !== "catalogue" && cited.add(s.slug));
    }
    l?.info?.resolved_scope.forEach((s) => cited.add(s.slug));
    const open = params.get("scope");
    return { recent_questions: recent, focus_slugs: [...cited].filter((s) => /^[a-z0-9][a-z0-9-]{0,120}$/.test(s)).slice(0, 6), open_slug: open ?? undefined };
  };

  const followUp = (q: string) => {
    run(q, { context: buildContext() });
    setParams((p) => {
      p.set("q", q);
      p.set("lang", i18n.language);
      return p;
    }, { replace: true });
    started.current = `${q}|${params.get("scope") ?? ""}`;
    window.setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }), 50);
  };

  // "Ask in हिंदी / ಕನ್ನಡ": switch the one language setting (UI, answer, voice) and ask the same question again.
  const askIn = (turn: Turn, l: Lang) => {
    void i18n.changeLanguage(l);
    run(turn.query, { context: turn.context, lang: l });
    setParams((p) => {
      p.set("lang", l);
      return p;
    }, { replace: true });
  };

  const clearScope = (turn: Turn) => {
    setParams((p) => {
      p.delete("scope");
      return p;
    }, { replace: true });
    run(turn.query, { context: { recent_questions: [], focus_slugs: [] } });
  };

  const quotes = useMemo(() => {
    const m = new Map<string, string>();
    focused?.answer?.points.forEach((p) => p.quote && p.citations.forEach((id) => !m.has(id) && m.set(id, p.quote!)));
    return m;
  }, [focused?.answer]);
  const citedIds = useMemo(() => new Set((focused?.answer?.points ?? []).flatMap((p) => p.citations).concat((focused?.answer?.standards ?? []).flatMap((s) => s.citations))), [focused?.answer]);

  if (!params.get("q") && turns.length === 0) {
    return (
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-4 text-2xl font-semibold">{t("ask.emptyTitle")}</h1>
        <SearchBar onSubmit={(q) => nav(`/ask?q=${encodeURIComponent(q)}&lang=${i18n.language}`)} autoFocus />
      </div>
    );
  }

  const activate = (turnId: number, cid: string) => {
    setFocusId(turnId);
    setProofOpen((o) => ({ ...o, [turnId]: true }));
    window.setTimeout(() => focusEvidence(cid), 80);
  };


  const refused = (a: Answer | null) => !!a && (a.answer_type === "insufficient_evidence" || a.answer_type === "out_of_scope");
  // The evidence column appears only once the user opens the proof for the focused answer.
  // One evidence list in the page: beside the answer on wide screens, inside the details on phones.
  const showAside = wide && !!focused && !!proofOpen[focused.id] && !!focused.answer && !refused(focused.answer);

  const evidenceList = (turn: Turn, headingId: string) => (
    <div>
      <SectionTitle id={headingId} right={<RetrievalDrawer trace={turn.trace} />}>
        <span className="inline-flex items-center gap-1.5">
          <Layers size={13} aria-hidden />
          {t("ask.evidenceTitle", { count: turn.evidence?.citations.length ?? 0 })}
        </span>
      </SectionTitle>
      {!turn.evidence || turn.evidence.citations.length === 0 ? (
        <p className="rounded-lg border border-calm-line bg-calm-bg p-3 text-[14px] text-calm-ink">{t("ask.noEvidence")}</p>
      ) : (
        <div className="space-y-3">
          {turn.evidence.citations.map((c) => (
            <EvidenceCard key={c.id} c={c} quote={turn.id === focused?.id ? quotes.get(c.id) : undefined} cited={turn.id === focused?.id && focused.answer ? citedIds.has(c.id) : undefined} />
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div>
      <div className={showAside ? "grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:gap-8" : "mx-auto max-w-3xl"}>
        <div className="min-w-0 space-y-8">
          {turns.map((turn, i) => {
            const cmap = new Map<string, Citation>((turn.evidence?.citations ?? []).map((c) => [c.id, c]));
            return (
              <CitationActivateContext.Provider key={turn.id} value={(cid: string) => activate(turn.id, cid)}>
              <article className={`space-y-4 ${i > 0 ? "border-t border-line pt-8" : ""}`} aria-labelledby={`q-${turn.id}`} onFocusCapture={() => setFocusId(turn.id)} onMouseDown={() => setFocusId(turn.id)}>
                <header className="space-y-2">
                  <h1 id={`q-${turn.id}`} lang={turn.lang} className={`${i === 0 ? "text-2xl" : "text-xl"} font-semibold leading-snug`}>
                    {turn.query}
                  </h1>
                  <div className="flex flex-wrap items-center gap-2">
                    {turn.info && <ScopeChip query={turn.info} onClear={turn.info.resolved_scope.length ? () => clearScope(turn) : undefined} />}
                    {turn.info && turn.info.lang !== "en" && turn.info.rewritten && (
                      <span className="text-xs text-ink-3" lang="en">
                        {t("ask.searchedAs")} “{turn.info.interpreted_query}”
                      </span>
                    )}
                  </div>
                </header>

                {turn.error ? (
                  <ErrorState messageKey={turn.error} onRetry={() => run(turn.query, { context: turn.context })} />
                ) : !turn.answer ? (
                  <>
                    <StageProgress stage={turn.stage} counts={{ sources: turn.stageDetail.sources, passages: turn.evidence?.citations.length }} />
                    {turn.evidence && (
                      <p className="text-[14px] text-ink-2" aria-live="polite">
                        {t("ask.foundEvidence", { k: turn.evidence.citations.length, s: new Set(turn.evidence.citations.map((c) => c.slug)).size })}
                      </p>
                    )}
                    <div className="space-y-2" aria-hidden>
                      <Skeleton className="h-4 w-11/12" />
                      <Skeleton className="h-4 w-10/12" />
                      <Skeleton className="h-4 w-8/12" />
                    </div>
                  </>
                ) : (
                  <>
                    <AnswerBlock
                      answer={turn.answer}
                      citations={cmap}
                      onFollowUp={i === turns.length - 1 ? followUp : undefined}
                      onPickOption={(o) => followUp(t("clarify.productQuery", { product: o }))}
                      onAskIn={i === turns.length - 1 ? (l) => askIn(turn, l) : undefined}
                      proofOpen={!!proofOpen[turn.id]}
                      onToggleProof={() => {
                        setFocusId(turn.id);
                        setProofOpen((o) => ({ ...o, [turn.id]: !o[turn.id] }));
                      }}
                      evidence={wide ? undefined : evidenceList(turn, `evidence-inline-${turn.id}`)}
                    />
                    {(proofOpen[turn.id] || refused(turn.answer)) && (
                      <p className="text-xs text-ink-3">
                        {t("ask.scopeNote")}
                        {turn.answer.synthetic_used ? ` ${t("ask.syntheticNote")}` : ""}
                      </p>
                    )}
                  </>
                )}
              </article>
              </CitationActivateContext.Provider>
            );
          })}

          {last?.done && (
            <div className="border-t border-line pt-4 lg:border-0 lg:pt-0">
              <SearchBar ref={followRef} size="md" initial="" onSubmit={followUp} label={t("ask.followUpLabel")} placeholder={t("ask.followUpPlaceholder")} slashShortcut={false} />
            </div>
          )}
        </div>

        {showAside && focused && (
          <aside className="min-w-0" aria-labelledby="evidence-title">
            <div className="lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto lg:pr-1">
              {turns.length > 1 && (
                <p className="mb-2 truncate text-xs text-ink-3" lang={focused.lang}>
                  {t("ask.evidenceFor")} “{focused.query}”
                </p>
              )}
              {evidenceList(focused, "evidence-title")}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
