// /ask — evidence-first question answering with a follow-up thread.
// Order on screen: stage progress -> evidence (as soon as retrieval returns) -> validated answer.
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
  const [mobileTab, setMobileTab] = useState<"answer" | "evidence">("answer");
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
      setMobileTab("answer");
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
    setMobileTab("evidence");
    window.setTimeout(() => focusEvidence(cid), 60);
  };

  const evidenceCount = focused?.evidence?.citations.length ?? 0;

  return (
    <div>
      {/* Mobile / tablet tabs */}
      <div role="tablist" aria-label={t("ask.viewTabs")} className="sticky top-14 z-20 -mx-4 mb-4 flex border-b border-line bg-page px-4 lg:hidden">
        {(["answer", "evidence"] as const).map((tab) => (
          <button
            key={tab}
            role="tab"
            type="button"
            aria-selected={mobileTab === tab}
            onClick={() => setMobileTab(tab)}
            className={`h-11 flex-1 border-b-2 text-[14px] font-medium ${mobileTab === tab ? "border-accent text-ink" : "border-transparent text-ink-3"}`}
          >
            {tab === "answer" ? t("ask.tabAnswer") : t("ask.tabEvidence", { count: evidenceCount })}
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:gap-8">
        <div className={`${mobileTab === "answer" ? "" : "hidden"} min-w-0 space-y-8 lg:block`}>
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
                    />
                    <p className="text-xs text-ink-3">
                      {t("ask.scopeNote")}
                      {turn.answer.synthetic_used ? ` ${t("ask.syntheticNote")}` : ""}
                    </p>
                  </>
                )}
              </article>
              </CitationActivateContext.Provider>
            );
          })}

          {last?.done && (
            <div className="sticky bottom-0 z-10 -mx-4 border-t border-line bg-page px-4 pb-3 pt-3 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:px-0 lg:pb-0">
              <SearchBar ref={followRef} size="md" initial="" onSubmit={followUp} label={t("ask.followUpLabel")} placeholder={t("ask.followUpPlaceholder")} slashShortcut={false} />
            </div>
          )}
        </div>

        <aside className={`${mobileTab === "evidence" ? "" : "hidden"} min-w-0 lg:block`} aria-labelledby="evidence-title">
          <div className="lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto lg:pr-1">
            <SectionTitle id="evidence-title" right={<RetrievalDrawer trace={focused?.trace ?? null} />}>
              <span className="inline-flex items-center gap-1.5">
                <Layers size={13} aria-hidden />
                {t("ask.evidenceTitle", { count: evidenceCount })}
              </span>
            </SectionTitle>
            {turns.length > 1 && focused && (
              <p className="mb-2 truncate text-xs text-ink-3" lang={focused.lang}>
                {t("ask.evidenceFor")} “{focused.query}”
              </p>
            )}
            {!focused?.evidence ? (
              focused?.error ? null : (
                <div className="space-y-3" aria-busy="true">
                  {[0, 1, 2].map((k) => (
                    <div key={k} className="card space-y-2 p-3.5">
                      <Skeleton className="h-4 w-1/2" />
                      <Skeleton className="h-3 w-3/4" />
                      <Skeleton className="h-12 w-full" />
                    </div>
                  ))}
                </div>
              )
            ) : focused.evidence.citations.length === 0 ? (
              <p className="rounded-lg border border-calm-line bg-calm-bg p-3 text-[14px] text-calm-ink">{t("ask.noEvidence")}</p>
            ) : (
              <div className="space-y-3">
                {focused.evidence.citations.map((c) => (
                  <EvidenceCard key={c.id} c={c} quote={quotes.get(c.id)} cited={focused.answer ? citedIds.has(c.id) : undefined} />
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
