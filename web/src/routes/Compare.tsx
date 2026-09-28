// /compare?a=&b= — aligned two-standard comparison. Every cell cites a source or says
// "Not found in the source". Numeric limits are aligned deterministically and shown verbatim.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Columns2, Info, Lightbulb } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { Citation, CompareResponse, Lang, SuggestItem } from "../api/types";
import { StandardPicker } from "../components/StandardPicker";
import { CitationActivateContext, CitationChip, EvidenceCard, focusEvidence } from "../components/Evidence";
import { EmptyState, ErrorState, SectionTitle, Skeleton, SyntheticBadge } from "../components/ui";
import { shortTitle } from "../lib/format";
import { useHealth } from "../lib/hooks";

export default function Compare() {
  const { t, i18n } = useTranslation();
  const health = useHealth();
  // Example pair that exists in the loaded data: the sample pair, or two official helmet product manuals.
  const example =
    health.data?.dataset_mode === "sample"
      ? { to: "/compare?a=demo-101-2026&b=demo-102-2026", label: "compare.example" }
      : (health.data?.counts?.standards_with_manual ?? 0) >= 2
        ? { to: "/compare?a=is-4151-2015&b=is-2925-1984", label: "compare.exampleOfficial" }
        : null;
  const [params, setParams] = useSearchParams();
  const a = params.get("a");
  const b = params.get("b");
  const [pa, setPa] = useState<SuggestItem | null>(null);
  const [pb, setPb] = useState<SuggestItem | null>(null);
  const q = useQuery({
    queryKey: ["compare", a, b, i18n.language],
    queryFn: () => api.compare(a!, b!, i18n.language as Lang),
    enabled: Boolean(a && b && a !== b),
    staleTime: Infinity,
    retry: false,
  });
  const setPair = (x: SuggestItem | null, y: SuggestItem | null) => {
    if (x && y && x.slug !== y.slug) setParams({ a: x.slug, b: y.slug });
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("compare.title")}</h1>
        <p className="text-[14px] text-ink-2">{t("compare.subtitle")}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <StandardPicker label={t("compare.a")} value={pa ?? (a && q.data ? toItem(q.data.a) : null)} exclude={b ?? undefined} onChange={(s) => { setPa(s); setPair(s, pb ?? (q.data ? toItem(q.data.b) : null)); }} />
        <StandardPicker label={t("compare.b")} value={pb ?? (b && q.data ? toItem(q.data.b) : null)} exclude={a ?? undefined} onChange={(s) => { setPb(s); setPair(pa ?? (q.data ? toItem(q.data.a) : null), s); }} />
        {example && (
          <Link to={example.to} className="inline-flex h-10 items-center text-[13px]">
            {t(example.label)}
          </Link>
        )}
      </div>

      {!a || !b ? (
        <EmptyState icon={<Columns2 size={20} aria-hidden />} title={t("compare.emptyTitle")} body={t("compare.emptyBody")} />
      ) : q.isLoading ? (
        <div className="space-y-2" aria-busy="true">
          <p className="text-[13px] text-ink-3" aria-live="polite">{t("compare.loading")}</p>
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : q.isError ? (
        <ErrorState messageKey={q.error instanceof ApiError ? q.error.messageKey : "error.internal"} onRetry={() => void q.refetch()} />
      ) : q.data ? (
        <CompareView data={q.data} />
      ) : null}
    </div>
  );
}

function toItem(s: CompareResponse["a"]): SuggestItem {
  return { slug: s.slug, number: s.number, title: s.title, kind: s.kind };
}

function CompareView({ data }: { data: CompareResponse }) {
  const { t } = useTranslation();
  const cmap = useMemo(() => new Map<string, Citation>(data.citations.map((c) => [c.id, c])), [data]);
  const [showSources, setShowSources] = useState(false);
  const activate = (id: string) => {
    setShowSources(true);
    window.setTimeout(() => focusEvidence(id), 60);
  };
  const head = (s: CompareResponse["a"]) => (
    <div>
      <Link to={`/standards/${s.slug}`} className="mono text-[15px] font-semibold">{s.number ?? shortTitle(s.title, 30)}</Link>
      <div className="text-xs font-normal normal-case tracking-normal text-ink-3">{shortTitle(s.title, 70)}</div>
      {s.synthetic && <div className="mt-1"><SyntheticBadge compact /></div>}
    </div>
  );
  return (
    <CitationActivateContext.Provider value={activate}>
      <div className="space-y-6">
        {data.mode === "extractive" && (
          <p className="flex items-start gap-2 rounded-md border border-calm-line bg-calm-bg px-3 py-2 text-[13px] text-calm-ink">
            <Info size={15} className="mt-0.5 shrink-0" aria-hidden />
            {t("compare.extractiveNote")}
          </p>
        )}
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[640px] border-collapse text-[14px]">
            <caption className="sr-only">{t("compare.tableCaption")}</caption>
            <thead className="sticky top-0 bg-surface-2 text-left">
              <tr>
                <th scope="col" className="w-44 px-3 py-2.5 text-xs uppercase tracking-wide text-ink-3">{t("compare.aspect")}</th>
                <th scope="col" className="px-3 py-2.5">{head(data.a)}</th>
                <th scope="col" className="px-3 py-2.5">{head(data.b)}</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.aspect} className="border-t border-line align-top">
                  <th scope="row" className="px-3 py-2.5 text-left text-[13px] font-semibold">{t(`compare.aspects.${r.aspect}`, { defaultValue: r.aspect })}</th>
                  {[r.a, r.b].map((cell, i) => (
                    <td key={i} className="px-3 py-2.5">
                      {cell.found ? (
                        <span>
                          {cell.text}
                          {cell.citations.map((id) => (
                            <CitationChip key={id} id={id} citations={cmap} />
                          ))}
                        </span>
                      ) : (
                        <span className="text-[13px] italic text-ink-3">{t("compare.notFound")}</span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data.numeric.length > 0 && (
          <section aria-labelledby="cmp-num">
            <SectionTitle id="cmp-num">{t("compare.numericTitle")}</SectionTitle>
            <p className="mb-2 text-[13px] text-ink-3">{t("compare.numericNote")}</p>
            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full min-w-[560px] text-[14px]">
                <thead className="bg-surface-2 text-left text-xs uppercase tracking-wide text-ink-3">
                  <tr>
                    <th scope="col" className="px-3 py-2">{t("compare.parameter")}</th>
                    <th scope="col" className="px-3 py-2">{t("compare.unit")}</th>
                    <th scope="col" className="mono px-3 py-2 normal-case">{data.a.number}</th>
                    <th scope="col" className="mono px-3 py-2 normal-case">{data.b.number}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.numeric.map((n) => {
                    const differs = n.a_value && n.b_value && n.a_value !== n.b_value;
                    return (
                      <tr key={n.parameter} className="border-t border-line">
                        <th scope="row" className="px-3 py-2 text-left font-medium">{n.parameter}</th>
                        <td className="px-3 py-2 text-ink-3">{n.unit ?? "—"}</td>
                        {[
                          [n.a_value, n.a_citation],
                          [n.b_value, n.b_citation],
                        ].map(([v, cid], i) => (
                          <td key={i} className={`mono tabular px-3 py-2 ${differs ? "bg-[#fffbe6]" : ""}`}>
                            {v ?? <span className="font-sans text-[13px] italic text-ink-3">{t("compare.notInTable")}</span>}
                            {v && cid && <CitationChip id={cid} citations={cmap} />}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-xs text-ink-3">{t("compare.differsLegend")}</p>
          </section>
        )}

        {data.key_differences.length > 0 && (
          <section className="rounded-lg border border-interp-line bg-interp-bg p-3">
            <div className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold text-interp-ink">
              <Lightbulb size={15} className="text-interp-icon" aria-hidden />
              {t("compare.keyDifferences")}
            </div>
            <ul className="space-y-1.5">
              {data.key_differences.map((p, i) => (
                <li key={i}>
                  {p.text}
                  {p.citations.map((id) => (
                    <CitationChip key={id} id={id} citations={cmap} />
                  ))}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <button type="button" onClick={() => setShowSources((s) => !s)} aria-expanded={showSources} className="text-[14px] font-medium text-accent hover:underline">
            {showSources ? t("compare.hideSources") : t("compare.showSources", { count: data.citations.length })}
          </button>
          {showSources && (
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              {data.citations.map((c) => (
                <EvidenceCard key={c.id} c={c} />
              ))}
            </div>
          )}
        </section>
      </div>
    </CitationActivateContext.Provider>
  );
}
