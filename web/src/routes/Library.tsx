// /standards — the library: filters, instant text filtering, sortable dense table (cards on mobile).
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search, SlidersHorizontal } from "lucide-react";
import { api } from "../api/client";
import type { StandardSummary } from "../api/types";
import { Badge, EmptyState, ErrorState, SectionTitle, Skeleton, SyntheticBadge } from "../components/ui";
import { CompulsoryBadge } from "../components/Answer";
import { useDebounced } from "../lib/hooks";
import { shortTitle } from "../lib/format";

const KIND_OPTIONS = [
  { value: "", key: "library.kindAll" },
  { value: "standard", key: "library.kindStandard" },
  { value: "guidance,order", key: "library.kindGuidance" },
  { value: "catalogue", key: "library.kindCatalogue" },
];

export default function Library() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") ?? "");
  const q = useDebounced(text, 150);
  const kind = params.get("kind") ?? "";
  const category = params.get("category") ?? "";
  const compulsory = params.get("compulsory") ?? "";
  const sort = params.get("sort") ?? "relevance";
  const page = Number(params.get("page") ?? "1") || 1;
  const [filtersOpen, setFiltersOpen] = useState(false);

  const set = (k: string, v: string) =>
    setParams((p) => {
      if (v) p.set(k, v);
      else p.delete(k);
      if (k !== "page") p.delete("page");
      return p;
    }, { replace: true });

  const list = useQuery({
    queryKey: ["standards", q, kind, category, compulsory, sort, page],
    queryFn: () => api.standards({ q, kind, category, compulsory, sort, page, page_size: 25 }),
    placeholderData: keepPreviousData,
  });
  const data = list.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const categories = useMemo(() => {
    const m = new Map<string, number>();
    (data?.facets.category ?? []).forEach((c) => m.set(c.category, (m.get(c.category) ?? 0) + c.count));
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 24);
  }, [data]);

  const Filters = (
    <div className="space-y-5">
      <fieldset>
        <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">{t("library.type")}</legend>
        <div className="space-y-0.5">
          {KIND_OPTIONS.map((o) => (
            <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-[14px] hover:bg-surface-2">
              <input type="radio" name="kind" checked={kind === o.value} onChange={() => set("kind", o.value)} className="accent-[var(--color-accent)]" />
              {t(o.key)}
              <span className="mono ml-auto text-xs text-ink-3">
                {o.value === "" ? "" : (data?.facets.kind ?? []).filter((k) => o.value.split(",").includes(k.category)).reduce((a, b) => a + b.count, 0) || ""}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">{t("library.compulsory")}</legend>
        <select value={compulsory} onChange={(e) => set("compulsory", e.target.value)} className="h-9 w-full rounded-md border border-line bg-surface px-2 text-[14px]" aria-label={t("library.compulsory")}>
          <option value="">{t("library.any")}</option>
          <option value="yes">{t("compulsory.yes")}</option>
          <option value="denotified">{t("compulsory.denotified")}</option>
          <option value="unknown">{t("library.notDetermined")}</option>
        </select>
        <p className="mt-1 text-xs text-ink-3">{t("library.compulsoryNote")}</p>
      </fieldset>
      <fieldset>
        <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">{t("library.category")}</legend>
        <div className="max-h-72 space-y-0.5 overflow-y-auto pr-1">
          <button type="button" onClick={() => set("category", "")} className={`block w-full rounded-md px-1.5 py-1 text-left text-[13px] ${category === "" ? "bg-accent-soft text-accent-strong" : "hover:bg-surface-2"}`}>
            {t("library.any")}
          </button>
          {categories.map(([c, n]) => (
            <button key={c} type="button" onClick={() => set("category", c)} className={`flex w-full items-baseline gap-2 rounded-md px-1.5 py-1 text-left text-[13px] ${category === c ? "bg-accent-soft text-accent-strong" : "hover:bg-surface-2"}`}>
              <span className="line-clamp-2 flex-1">{c}</span>
              <span className="mono text-xs text-ink-3">{n}</span>
            </button>
          ))}
        </div>
      </fieldset>
    </div>
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t("library.title")}</h1>
          <p className="text-[14px] text-ink-2">{t("library.subtitle")}</p>
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside aria-label={t("library.filters")} className="hidden lg:block">{Filters}</aside>
        <div className="min-w-0 space-y-3">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search size={16} className="pointer-events-none absolute left-3 top-3 text-ink-3" aria-hidden />
              <label htmlFor="lib-q" className="sr-only">{t("library.searchLabel")}</label>
              <input
                id="lib-q"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  set("q", e.target.value);
                }}
                placeholder={t("library.searchPlaceholder")}
                className="h-10 w-full rounded-md border border-line-strong bg-surface pl-9 pr-3 text-[15px] outline-none focus:border-accent"
              />
            </div>
            <button type="button" className="inline-flex h-10 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 text-[14px] lg:hidden" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((o) => !o)}>
              <SlidersHorizontal size={15} aria-hidden />
              {t("library.filters")}
            </button>
            <label className="sr-only" htmlFor="lib-sort">{t("library.sort")}</label>
            <select id="lib-sort" value={sort} onChange={(e) => set("sort", e.target.value)} className="hidden h-10 rounded-md border border-line-strong bg-surface px-2 text-[14px] sm:block">
              <option value="relevance">{t("library.sortRelevance")}</option>
              <option value="number">{t("library.sortNumber")}</option>
              <option value="title">{t("library.sortTitle")}</option>
              <option value="year">{t("library.sortYear")}</option>
            </select>
          </div>
          {filtersOpen && <div className="card p-4 lg:hidden">{Filters}</div>}

          <p className="text-[13px] text-ink-3" aria-live="polite">
            {data ? t("library.results", { count: data.total }) : " "}
          </p>

          {list.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : list.isError ? (
            <ErrorState messageKey="error.backend_down" onRetry={() => void list.refetch()} />
          ) : !data || data.items.length === 0 ? (
            <EmptyState title={t("library.emptyTitle")} body={t("library.emptyBody")} />
          ) : (
            <>
              <div className="card hidden overflow-hidden md:block">
                <table className="w-full text-left text-[14px]">
                  <caption className="sr-only">{t("library.title")}</caption>
                  <thead className="bg-surface-2 text-xs uppercase tracking-wide text-ink-3">
                    <tr>
                      <th scope="col" className="px-3 py-2 font-semibold">{t("library.colNumber")}</th>
                      <th scope="col" className="px-3 py-2 font-semibold">{t("library.colTitle")}</th>
                      <th scope="col" className="px-3 py-2 font-semibold">{t("library.colType")}</th>
                      <th scope="col" className="px-3 py-2 font-semibold">{t("library.colStatus")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((s) => (
                      <Row key={s.slug} s={s} />
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="space-y-2 md:hidden">
                {data.items.map((s) => (
                  <li key={s.slug}>
                    <Link to={`/standards/${s.slug}`} className="card block p-3 text-ink no-underline">
                      <div className="flex flex-wrap items-center gap-2">
                        {s.number && <span className="mono text-[14px] font-semibold">{s.number}</span>}
                        {s.synthetic && <SyntheticBadge compact />}
                        <CompulsoryBadge status={s.compulsory} />
                      </div>
                      <div className="mt-0.5 text-[14px]">{shortTitle(s.title, 110)}</div>
                      <div className="mt-1 text-xs text-ink-3">
                        {t(`kind.${s.kind}`)} {s.category ? `· ${s.category}` : ""}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
              <nav aria-label={t("library.pagination")} className="flex items-center justify-between pt-1">
                <button type="button" disabled={page <= 1} onClick={() => set("page", String(page - 1))} className="inline-flex h-9 items-center gap-1 rounded-md border border-line bg-surface px-3 text-[13px] disabled:opacity-40">
                  <ChevronLeft size={15} aria-hidden />
                  {t("library.prev")}
                </button>
                <span className="text-[13px] text-ink-3">{t("library.pageOf", { page, pages })}</span>
                <button type="button" disabled={page >= pages} onClick={() => set("page", String(page + 1))} className="inline-flex h-9 items-center gap-1 rounded-md border border-line bg-surface px-3 text-[13px] disabled:opacity-40">
                  {t("library.next")}
                  <ChevronRight size={15} aria-hidden />
                </button>
              </nav>
            </>
          )}
        </div>
      </div>
      <div className="mt-6">
        <SectionTitle>{t("library.aboutTypes")}</SectionTitle>
        <p className="max-w-3xl text-[13px] text-ink-3">{t("library.aboutTypesBody")}</p>
      </div>
    </div>
  );
}

function Row({ s }: { s: StandardSummary }) {
  const { t } = useTranslation();
  return (
    <tr className="border-t border-line align-top hover:bg-surface-2">
      <td className="whitespace-nowrap px-3 py-2.5">
        <Link to={`/standards/${s.slug}`} className="mono font-semibold">
          {s.number ?? "—"}
        </Link>
      </td>
      <td className="px-3 py-2.5">
        <Link to={`/standards/${s.slug}`} className="text-ink no-underline hover:text-accent">
          {shortTitle(s.title, 120)}
        </Link>
        {s.category && <div className="text-xs text-ink-3">{s.category}</div>}
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-[13px]">
        <div className="flex flex-col items-start gap-1">
          <Badge>{t(`kind.${s.kind}`)}</Badge>
          {s.synthetic && <SyntheticBadge compact />}
        </div>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-col items-start gap-1">
          <CompulsoryBadge status={s.compulsory} />
          {s.catalogue_only && <span className="text-xs text-ink-3">{t("standard.catalogueOnlyShort")}</span>}
          {!s.catalogue_only && s.requirement_count > 0 && <span className="text-xs text-ink-3">{t("library.reqCount", { count: s.requirement_count })}</span>}
        </div>
      </td>
    </tr>
  );
}
