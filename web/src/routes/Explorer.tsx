// /standards/:slug — the standard explorer.
// "At a glance" card, then tabs: Overview · Important requirements · Full text & clauses · Related & compare · Ask. Deep links: ?tab=clauses&clause=4.3.1
// scroll to and highlight the clause (citation clicks land here).
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
import { AlertCircle, ArrowRight, Columns2, ExternalLink, FileText, Image as ImageIcon, Scale, Sparkles } from "lucide-react";
import { api } from "../api/client";
import type { ClauseNode, ClauseOut, StandardDetail } from "../api/types";
import { Markdown } from "../components/Markdown";
import { Badge, Button, EmptyState, ErrorState, SectionTitle, Skeleton, SourceBadge, SyntheticBadge } from "../components/ui";
import { AnswerBlock, CompulsoryBadge } from "../components/Answer";
import { EvidenceCard } from "../components/Evidence";
import { SearchBar } from "../components/SearchBar";
import { PagePreviewDialog } from "../components/PagePreview";
import { ApiError } from "../api/client";
import { clauseAnchor, clauseTitle, shortTitle } from "../lib/format";
import { pushRecentStandard } from "../lib/storage";
import { RequirementsPanel } from "./Requirements";

const TABS = ["overview", "requirements", "clauses", "references", "ask"] as const;
type Tab = (typeof TABS)[number];

export default function Explorer() {
  const { slug = "" } = useParams();
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const detail = useQuery({ queryKey: ["standard", slug], queryFn: () => api.standard(slug), retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 1 });
  const d = detail.data;

  useEffect(() => {
    if (d) pushRecentStandard({ slug: d.summary.slug, number: d.summary.number, title: d.summary.title, kind: d.summary.kind });
  }, [d]);
  useEffect(() => {
    if (d) document.title = `${d.summary.number ?? shortTitle(d.summary.title, 50)} — BISense`;
    return () => {
      document.title = "BISense — evidence-first assistant for Indian Standards";
    };
  }, [d]);

  if (detail.isLoading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (detail.isError) {
    const e = detail.error;
    if (e instanceof ApiError && e.status === 404) {
      return <EmptyState title={t("explorer.notFound")} body={t("explorer.notFoundBody")} action={<Link to="/standards">{t("home.browseAll")}</Link>} />;
    }
    return <ErrorState messageKey={e instanceof ApiError ? e.messageKey : "error.internal"} onRetry={() => void detail.refetch()} />;
  }
  if (!d) return null;

  const s = d.summary;
  const hasReq = s.requirement_count > 0;
  const tabs: Tab[] = s.catalogue_only ? ["overview"] : TABS.filter((x) => x !== "requirements" || hasReq).filter((x) => x !== "references" || s.kind === "standard");
  const tab = (tabs.includes(params.get("tab") as Tab) ? params.get("tab") : "overview") as Tab;
  const setTab = (v: string) =>
    setParams((p) => {
      p.set("tab", v);
      if (v !== "clauses") p.delete("clause");
      return p;
    });

  return (
    <div>
      <Header d={d} />
      <Tabs.Root value={tab} onValueChange={setTab} className="mt-5">
        <Tabs.List aria-label={t("explorer.sections")} className="-mx-4 flex gap-1 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0">
          {tabs.map((x) => (
            <Tabs.Trigger
              key={x}
              value={x}
              className="h-11 shrink-0 border-b-2 border-transparent px-3 text-[14px] font-medium text-ink-3 hover:text-ink data-[state=active]:border-accent data-[state=active]:text-ink"
            >
              {t(`explorer.tab.${x}${x === "requirements" && s.kind !== "standard" ? "Obligations" : ""}`)}
              {x === "requirements" && <span className="mono ml-1.5 text-xs text-ink-3">{s.requirement_count}</span>}
              {x === "clauses" && <span className="mono ml-1.5 text-xs text-ink-3">{s.clause_count}</span>}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="overview" className="pt-5 outline-none">
          <Overview d={d} onTab={setTab} />
        </Tabs.Content>
        {!s.catalogue_only && (
          <>
            <Tabs.Content value="clauses" className="pt-5 outline-none">
              {tab === "clauses" && <ClauseViewer d={d} target={params.get("clause")} />}
            </Tabs.Content>
            {hasReq && (
              <Tabs.Content value="requirements" className="pt-5 outline-none">
                {tab === "requirements" && <RequirementsPanel d={d} />}
              </Tabs.Content>
            )}
            <Tabs.Content value="references" className="pt-5 outline-none">
              <References d={d} />
            </Tabs.Content>
            <Tabs.Content value="ask" className="pt-5 outline-none">
              <ScopedAsk d={d} />
            </Tabs.Content>
          </>
        )}
      </Tabs.Root>
    </div>
  );
}

/** First sentence of the scope text, for the "What it covers" line. */
function firstSentence(text: string | null | undefined, max = 240): string | null {
  if (!text) return null;
  const flat = text.replace(/\s+/g, " ").trim();
  const m = flat.match(/^.+?[.;](?=\s|$)/);
  const out = m ? m[0] : flat;
  return out.length > max ? `${out.slice(0, max - 1)}…` : out;
}

function Header({ d }: { d: StandardDetail }) {
  const { t } = useTranslation();
  const s = d.summary;
  const p = d.provenance;
  const covers = firstSentence(d.scope_text);
  const who = d.products.length ? d.products.slice(0, 5).join(", ") : d.industries.join(", ");
  return (
    <header className={`rounded-lg border border-line bg-surface p-4 sm:p-5 ${s.synthetic ? "synthetic-stripes" : ""}`} aria-labelledby="std-title">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-3">{t("glance.title")}</p>
      <h1 id="std-title" className="mt-1 max-w-4xl text-[22px] font-semibold leading-snug sm:text-[26px]">
        {shortTitle(s.title, 160)}
      </h1>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
        {s.number && <span className="mono text-[15px] font-semibold text-ink-2">{s.number}</span>}
        {s.synthetic ? <SyntheticBadge /> : <SourceBadge type={s.source_type} />}
        {s.kind !== "standard" && <Badge>{t(`kind.${s.kind}`)}</Badge>}
        {s.catalogue_only && <Badge tone="calm">{t("standard.catalogueOnly")}</Badge>}
        <CompulsoryBadge status={s.compulsory} source={d.compulsory.source} />
        {s.needs_review && (
          <Badge tone="warn">
            <AlertCircle size={12} aria-hidden />
            {t("standard.needsReview")}
          </Badge>
        )}
      </div>
      <dl className="mt-4 grid gap-x-6 gap-y-3 text-[14px] sm:grid-cols-2">
        {covers && (
          <div className="sm:col-span-2">
            <dt className="text-xs font-semibold text-ink-3">{t("glance.covers")}</dt>
            <dd className="mt-0.5 text-ink">{covers}</dd>
          </div>
        )}
        {who && (
          <div>
            <dt className="text-xs font-semibold text-ink-3">{t("glance.who")}</dt>
            <dd className="mt-0.5 text-ink">{who}</dd>
          </div>
        )}
        <div>
          <dt className="text-xs font-semibold text-ink-3">{t("glance.status")}</dt>
          <dd className="mt-0.5 text-ink">
            {t(`status.${s.status}`, { defaultValue: s.status })}
            {d.revision_label ? ` · ${d.revision_label}` : ""}
            <span className="text-ink-3">{d.status_verified_on ? ` · ${t("standard.verifiedOn", { date: d.status_verified_on })}` : ` · ${t("standard.statusUnverified")}`}</span>
          </dd>
        </div>
      </dl>
      <details className="mt-3 text-[13px] text-ink-3">
        <summary className="inline-flex min-h-9 cursor-pointer items-center font-medium text-ink-2">{t("glance.sourceDetails")}</summary>
        <dl className="mt-1 flex flex-wrap gap-x-5 gap-y-1">
          {s.category && (
            <div>
              <dt className="inline">{t("standard.category")}: </dt>
              <dd className="inline text-ink-2">{s.category}</dd>
            </div>
          )}
          {d.committee && (
            <div>
              <dt className="inline">{t("standard.committee")}: </dt>
              <dd className="inline text-ink-2">{d.committee}</dd>
            </div>
          )}
          <div>
            <dt className="inline">{t("standard.provenance")}: </dt>
            <dd className="inline text-ink-2">
              {t(`tier.${p.tier}`)}
              {p.obtained_on ? ` · ${t("standard.obtainedOn", { date: p.obtained_on })}` : ""}
              {p.pages ? ` · ${t("standard.pagesCount", { count: p.pages })}` : ""}
            </dd>
          </div>
          {p.source_url ? (
            <div>
              <a href={p.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1">
                <ExternalLink size={13} aria-hidden />
                {t("standard.officialSource")}
              </a>
            </div>
          ) : (
            !s.synthetic && <div>{t("evidence.noLink")}</div>
          )}
        </dl>
      </details>
    </header>
  );
}

function Overview({ d, onTab }: { d: StandardDetail; onTab: (t: string) => void }) {
  const { t, i18n } = useTranslation();
  const s = d.summary;
  const [wantSummary, setWantSummary] = useState(false);
  const summary = useQuery({ queryKey: ["summary", s.slug, i18n.language], queryFn: () => api.summary(s.slug, i18n.language as "en"), enabled: wantSummary, staleTime: Infinity });
  const cmap = useMemo(() => new Map((summary.data?.citations ?? []).map((c) => [c.id, c])), [summary.data]);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="min-w-0 space-y-6">
        {s.catalogue_only ? (
          <div className="rounded-lg border border-calm-line bg-calm-bg p-4 text-calm-ink">
            <p className="font-semibold">{t("standard.catalogueOnlyTitle")}</p>
            <p className="mt-1 text-[14px]">{t("standard.catalogueOnlyBody")}</p>
          </div>
        ) : (
          <section aria-labelledby="ov-scope">
            <SectionTitle id="ov-scope">{s.kind === "standard" ? t("explorer.scope") : t("explorer.about")}</SectionTitle>
            {d.scope_text ? (
              <div className="card border-l-[3px] border-l-fact-rule p-4">
                <Markdown text={d.scope_text} className="text-[15px] leading-relaxed" />
                {d.scope_clause && (
                  <Link to={`?tab=clauses&clause=${encodeURIComponent(d.scope_clause)}`} className="mt-2 inline-flex items-center gap-1 text-[13px]">
                    <FileText size={13} aria-hidden />
                    {t("explorer.clauseRef", { n: d.scope_clause })}
                  </Link>
                )}
              </div>
            ) : (
              <p className="text-ink-3">{t("explorer.noScope")}</p>
            )}
          </section>
        )}

        {!s.catalogue_only && (
          <section aria-labelledby="ov-summary">
            <SectionTitle id="ov-summary">{t("explorer.plainSummary")}</SectionTitle>
            {!wantSummary ? (
              <Button onClick={() => setWantSummary(true)}>
                <Sparkles size={15} aria-hidden />
                {t("explorer.generateSummary")}
              </Button>
            ) : summary.isLoading ? (
              <div className="space-y-2" aria-busy="true">
                <p className="text-[13px] text-ink-3" aria-live="polite">{t("explorer.summaryLoading")}</p>
                <Skeleton className="h-4 w-11/12" />
                <Skeleton className="h-4 w-9/12" />
                <Skeleton className="h-4 w-10/12" />
              </div>
            ) : summary.isError ? (
              <ErrorState messageKey={summary.error instanceof ApiError ? summary.error.messageKey : "error.internal"} onRetry={() => void summary.refetch()} />
            ) : summary.data ? (
              <div className="space-y-4">
                <AnswerBlock answer={summary.data.answer} citations={cmap} />
                <details className="rounded-lg border border-line bg-surface p-3">
                  <summary className="cursor-pointer text-[13px] font-medium">{t("explorer.summarySources", { count: summary.data.citations.length })}</summary>
                  <div className="mt-3 space-y-3">
                    {summary.data.citations.map((c) => (
                      <EvidenceCard key={c.id} c={c} />
                    ))}
                  </div>
                </details>
              </div>
            ) : null}
          </section>
        )}

        {d.amendments.length > 0 && (
          <section aria-labelledby="ov-amend">
            <SectionTitle id="ov-amend">{t("explorer.amendments")}</SectionTitle>
            <ul className="space-y-2">
              {d.amendments.map((a) => (
                <li key={a.label} className="card p-3">
                  <div className="flex items-center gap-2 text-[14px] font-medium">
                    <span className="mono">{a.label}</span>
                    {a.date && <span className="text-ink-3">· {a.date}</span>}
                  </div>
                  {a.text_excerpt && <p className="mt-1 text-[14px] text-ink-2">{a.text_excerpt}</p>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <div className="min-w-0 space-y-6">
        <section aria-labelledby="ov-legal">
          <SectionTitle id="ov-legal">{t("legal.title")}</SectionTitle>
          <div className="card divide-y divide-line">
            <div className="p-3.5">
              <div className="flex items-center gap-2 text-[14px] font-semibold">
                <Scale size={15} className="text-warn-ink" aria-hidden />
                {t("legal.compulsoryTitle")}
              </div>
              {d.compulsory.status === "yes" || d.compulsory.status === "denotified" ? (
                <p className="mt-1 text-[14px]">
                  {t(d.compulsory.status === "yes" ? "legal.listedCompulsory" : "legal.listedDenotified")}{" "}
                  {d.compulsory.slug && (
                    <Link to={`/standards/${d.compulsory.slug}?tab=clauses&clause=${encodeURIComponent(d.compulsory.clause_number ?? "")}`}>{t("legal.seeListEntry")}</Link>
                  )}
                  {d.compulsory.source && <span className="mt-1 block text-[13px] text-ink-3">{d.compulsory.source}</span>}
                </p>
              ) : (
                <p className="mt-1 text-[14px] text-ink-2">{t("legal.notDetermined")}</p>
              )}
            </div>
            {s.kind === "standard" && (
              <div className="p-3.5">
                <div className="text-[14px] font-semibold">{t("legal.shallTitle")}</div>
                <p className="mt-1 text-[14px] text-ink-2">{t("legal.shallBody")}</p>
              </div>
            )}
          </div>
        </section>

        {d.product_mentions.length > 0 && (
          <section aria-labelledby="ov-products">
            <SectionTitle id="ov-products">{t("explorer.productMentions")}</SectionTitle>
            <ul className="card divide-y divide-line">
              {d.product_mentions.map((m, i) => (
                <li key={i} className="p-3 text-[14px]">
                  <div className="font-medium">{m.product}</div>
                  <div className="text-[13px] text-ink-3">{m.status === "denotified" ? t("compulsory.denotified") : m.order}</div>
                  {m.slug && (
                    <Link className="text-[13px]" to={`/standards/${m.slug}?tab=clauses&clause=${encodeURIComponent(m.clause_number ?? "")}`}>
                      {t("legal.seeListEntry")}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {!s.catalogue_only && (
          <section aria-labelledby="ov-sections">
            <SectionTitle id="ov-sections" right={<button type="button" className="text-[13px] text-accent hover:underline" onClick={() => onTab("clauses")}>{t("explorer.allClauses")}</button>}>
              {t("explorer.keySections")}
            </SectionTitle>
            <ul className="card divide-y divide-line">
              {d.clauses.slice(0, 14).map((c) => (
                <li key={c.id}>
                  <Link to={`?tab=clauses&clause=${encodeURIComponent(c.number)}`} className="flex items-baseline gap-2 px-3 py-2 text-[14px] text-ink no-underline hover:bg-surface-2">
                    <span className="mono w-16 shrink-0 text-[13px] text-ink-3">{clauseTitle(c.number, c.heading).num ?? ""}</span>
                    <span className="flex-1 truncate">{clauseTitle(c.number, c.heading).text || t(`clauseKind.${c.kind}`, { defaultValue: c.kind })}</span>
                    {c.children.length > 0 && <span className="text-xs text-ink-3">{c.children.length}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {d.terms.length > 0 && (
          <section aria-labelledby="ov-terms">
            <SectionTitle id="ov-terms">{t("explorer.terms")}</SectionTitle>
            <dl className="card divide-y divide-line">
              {d.terms.map((term) => (
                <div key={String(term.term)} className="p-3 text-[14px]">
                  <dt className="font-semibold">
                    {term.term} <span className="mono text-xs font-normal text-ink-3">{term.clause_number}</span>
                  </dt>
                  <dd className="text-ink-2">{term.definition}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}
      </div>
    </div>
  );
}

function flatten(nodes: ClauseNode[], out: ClauseNode[] = []): ClauseNode[] {
  for (const n of nodes) {
    out.push(n);
    flatten(n.children, out);
  }
  return out;
}

function ClauseViewer({ d, target }: { d: StandardDetail; target: string | null }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["clauses", d.summary.slug], queryFn: () => api.clauses(d.summary.slug) });
  const [active, setActive] = useState<string | null>(target);
  const [preview, setPreview] = useState<ClauseOut | null>(null);
  const done = useRef<string | null>(null);
  const toc = useMemo(() => flatten(d.clauses), [d.clauses]);
  const hasPdf = (d.provenance.file_name ?? "").toLowerCase().endsWith(".pdf");

  useEffect(() => {
    if (!q.data || !target || done.current === target) return;
    const el = document.getElementById(clauseAnchor(target));
    if (el) {
      done.current = target;
      setActive(target);
      window.setTimeout(() => {
        el.scrollIntoView({ block: "start", behavior: "auto" });
        el.classList.remove("flash");
        void el.offsetWidth;
        el.classList.add("flash");
        el.focus({ preventScroll: true });
      }, 30);
    }
  }, [q.data, target]);

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError) return <ErrorState messageKey="error.internal" onRetry={() => void q.refetch()} />;
  const clauses = q.data ?? [];

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
      <nav aria-label={t("explorer.toc")} className="hidden lg:block">
        <div className="sticky top-20 max-h-[calc(100dvh-6rem)] overflow-y-auto pr-2">
          <ul className="space-y-0.5 text-[13px]">
            {toc.map((c) => (
              <li key={c.id}>
                <a
                  href={`#${clauseAnchor(c.number)}`}
                  onClick={() => setActive(c.number)}
                  className={`block truncate rounded-sm py-1 pr-2 no-underline hover:bg-surface-2 ${active === c.number ? "bg-accent-soft text-accent-strong" : "text-ink-2"}`}
                  style={{ paddingLeft: `${(c.level - 1) * 12 + 8}px` }}
                >
                  {clauseTitle(c.number, c.heading).num && <span className="mono">{c.number}</span>} {clauseTitle(c.number, c.heading).text}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </nav>
      <div className="min-w-0">
        {target && !clauses.some((c) => c.number === target) && (
          <p className="mb-3 rounded-md bg-warn-bg px-3 py-2 text-[13px] text-warn-ink">{t("explorer.clauseMissing", { n: target })}</p>
        )}
        {d.summary.synthetic && <p className="mb-3 text-[13px] text-synth-ink">{t("synthetic.inline")}</p>}
        <div className="space-y-1">
          {clauses.map((c) => (
            <section
              key={c.id}
              id={clauseAnchor(c.number)}
              tabIndex={-1}
              aria-labelledby={`${clauseAnchor(c.number)}-h`}
              className={`group scroll-mt-20 rounded-md px-3 py-2 outline-none ${target === c.number ? "bg-[#fffbe6] ring-1 ring-[#f1dc6b]" : ""}`}
              style={{ marginLeft: `${Math.min(c.level - 1, 3) * 14}px` }}
            >
              <div className="flex flex-wrap items-baseline gap-x-2">
                <h3 id={`${clauseAnchor(c.number)}-h`} className={`${c.level === 1 ? "text-[16px] font-semibold" : "text-[15px] font-medium"}`}>
                  {clauseTitle(c.number, c.heading).num && <span className="mono mr-2 text-ink-2">{c.number}</span>}
                  {clauseTitle(c.number, c.heading).text}
                </h3>
                <span className="text-xs text-ink-3">{hasPdf ? t("evidence.page", { n: c.page_start }) : ""}</span>
                {hasPdf && (
                  <button type="button" onClick={() => setPreview(c)} className="inline-flex h-7 items-center gap-1 rounded px-1.5 text-xs text-accent hover:bg-surface-2 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100 sm:focus-visible:opacity-100" aria-label={t("evidence.viewPageOf", { n: c.number })}>
                    <ImageIcon size={12} aria-hidden />
                    {t("evidence.viewPage")}
                  </button>
                )}
              </div>
              {c.text && <Markdown text={c.text} className="mt-1 text-[15px] leading-relaxed text-ink" />}
            </section>
          ))}
        </div>
      </div>
      {preview && (
        <PagePreviewDialog
          c={{ slug: d.summary.slug, page_start: preview.page_start, standard_number: d.summary.number, standard_title: d.summary.title, clause_number: preview.number, synthetic: d.summary.synthetic }}
          quote={preview.text.slice(0, 90)}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}

function References({ d }: { d: StandardDetail }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-5">
      <Link to={`/compare?a=${d.summary.slug}`} className="inline-flex min-h-10 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 text-[14px] font-medium text-ink no-underline hover:border-accent">
        <Columns2 size={15} aria-hidden />
        {t("next.compare")}
      </Link>
      <div className="grid gap-6 lg:grid-cols-3">
        <section aria-labelledby="ref-out">
          <SectionTitle id="ref-out">{t("refs.referencedByThis")}</SectionTitle>
          <p className="mb-2 text-[13px] text-ink-3">{t("refs.referencedByThisNote")}</p>
          {d.references.length === 0 ? (
            <p className="text-ink-3">{t("refs.none")}</p>
          ) : (
            <ul className="card divide-y divide-line">
              {d.references.map((r) => (
                <li key={r.number} className="flex items-baseline justify-between gap-2 p-3 text-[14px]">
                  <span>
                    {r.slug ? <Link to={`/standards/${r.slug}`} className="mono font-semibold">{r.number}</Link> : <span className="mono font-semibold">{r.number}</span>}
                    <span className="block text-[13px] text-ink-3">{r.title ? shortTitle(r.title, 70) : t("refs.notInLibrary")}</span>
                  </span>
                  {r.clause_number && <span className="mono text-xs text-ink-3">{t("refs.inClause", { n: r.clause_number })}</span>}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="ref-in">
          <SectionTitle id="ref-in">{t("refs.referencedBy")}</SectionTitle>
          {d.referenced_by.length === 0 ? (
            <p className="text-ink-3">{t("refs.none")}</p>
          ) : (
            <ul className="card divide-y divide-line">
              {d.referenced_by.map((r) => (
                <li key={r.number} className="p-3 text-[14px]">
                  {r.slug ? <Link to={`/standards/${r.slug}`} className="mono font-semibold">{r.number}</Link> : r.number}
                  {r.clause_number && <span className="mono ml-2 text-xs text-ink-3">{t("refs.inClause", { n: r.clause_number })}</span>}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="ref-sim">
          <SectionTitle id="ref-sim">{t("refs.similar")}</SectionTitle>
          <p className="mb-2 text-[13px] text-ink-3">{t("refs.similarNote")}</p>
          {d.related.length === 0 ? (
            <p className="text-ink-3">{t("refs.none")}</p>
          ) : (
            <ul className="card divide-y divide-line">
              {d.related.map((r) => (
                <li key={r.slug} className="flex items-center justify-between gap-2 p-3 text-[14px]">
                  <span className="min-w-0">
                    <Link to={`/standards/${r.slug}`} className="mono font-semibold">{r.number ?? shortTitle(r.title, 40)}</Link>
                    <span className="block truncate text-[13px] text-ink-3">{shortTitle(r.title, 70)}</span>
                  </span>
                  <span className="mono text-xs text-ink-3" title={t("refs.similarityScore")}>{r.similarity.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function ScopedAsk({ d }: { d: StandardDetail }) {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const label = d.summary.number ?? shortTitle(d.summary.title, 50);
  const go = (q: string) => nav(`/ask?q=${encodeURIComponent(q)}&lang=${i18n.language}&scope=${d.summary.slug}`);
  const suggestions = d.summary.kind === "standard"
    ? [t("explorer.askSuggest.requirements"), t("explorer.askSuggest.tests"), t("explorer.askSuggest.marking"), t("explorer.askSuggest.explain")]
    : [t("explorer.askSuggest.explain"), t("explorer.askSuggest.who"), t("explorer.askSuggest.fees")];
  return (
    <div className="max-w-3xl space-y-3">
      <p className="text-[14px] text-ink-2">{t("explorer.askIntro", { label })}</p>
      <SearchBar onSubmit={go} size="md" slashShortcut={false} label={t("explorer.askLabel", { label })} placeholder={t("explorer.askPlaceholder", { label })} />
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <button key={s} type="button" onClick={() => go(s)} className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-line bg-surface px-3 text-[13px] text-ink-2 hover:border-accent">
            {s}
            <ArrowRight size={13} aria-hidden />
          </button>
        ))}
      </div>
    </div>
  );
}
