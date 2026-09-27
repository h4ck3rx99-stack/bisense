// Requirements tab: deterministic requirement statements (no AI), filterable, grouped by clause,
// with CSV export, print view and an optional, clearly labelled AI plain-language toggle.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Download, Lightbulb, Printer, Search } from "lucide-react";
import { api, ApiError, csvUrl } from "../api/client";
import type { Lang, RequirementOut, StandardDetail } from "../api/types";
import { SectionTitle, Skeleton, ErrorState } from "../components/ui";
import { useDebounced } from "../lib/hooks";
import { clauseLink } from "../lib/format";

const MODALITIES = ["shall", "shall_not", "should", "should_not", "may", "must"] as const;

export function ModalityPill({ m }: { m: string }) {
  const { t } = useTranslation();
  const tone =
    m === "shall" || m === "must"
      ? "bg-ink text-white border-ink"
      : m === "shall_not" || m === "should_not"
        ? "bg-err-bg text-err-ink border-[#f2c9c9]"
        : m === "should"
          ? "bg-accent-soft text-accent-strong border-[#d6d3f3]"
          : "bg-surface-2 text-ink-2 border-line";
  return (
    <span className={`mono inline-flex h-5 shrink-0 items-center rounded-sm border px-1.5 text-[10.5px] font-semibold tracking-wide ${tone}`} title={t(`modality.${m}Help`)}>
      {t(`modality.${m}`)}
    </span>
  );
}

export function groupByClause(items: RequirementOut[]) {
  const groups: { clause: string; heading: string; kind: string; page: number; items: RequirementOut[] }[] = [];
  for (const it of items) {
    const g = groups[groups.length - 1];
    if (g && g.clause === it.clause_number) g.items.push(it);
    else groups.push({ clause: it.clause_number, heading: it.clause_heading, kind: it.clause_kind, page: it.page, items: [it] });
  }
  return groups;
}

export function RequirementsPanel({ d }: { d: StandardDetail }) {
  const { t, i18n } = useTranslation();
  const slug = d.summary.slug;
  const [modality, setModality] = useState<string[]>([]);
  const [kind, setKind] = useState("");
  const [text, setText] = useState("");
  const [plain, setPlain] = useState(false);
  const q = useDebounced(text, 200);
  const reqs = useQuery({
    queryKey: ["req", slug, modality.join(","), kind, q],
    queryFn: () => api.requirements(slug, { modality: modality.join(",") || undefined, kind: kind || undefined, q: q || undefined }),
    placeholderData: (prev) => prev,
  });
  const plainQ = useQuery({ queryKey: ["plain", slug, i18n.language], queryFn: () => api.plain(slug, i18n.language as Lang), enabled: plain, staleTime: Infinity, retry: false });
  const groups = useMemo(() => groupByClause(reqs.data?.items ?? []), [reqs.data]);
  const kinds = useMemo(() => [...new Set((reqs.data?.items ?? []).map((r) => r.topic))], [reqs.data]);
  const isStandard = d.summary.kind === "standard";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-[14px] text-ink-2">
          {t(isStandard ? "req.header" : "req.headerGuidance", { label: d.summary.number ?? d.summary.title })}
        </p>
        <RequirementsActions slug={slug} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t("req.filterModality")} className="flex flex-wrap gap-1">
          {MODALITIES.filter((m) => (reqs.data?.counts?.[m] ?? 0) > 0 || modality.includes(m)).map((m) => {
            const on = modality.includes(m);
            return (
              <button key={m} type="button" aria-pressed={on} onClick={() => setModality((xs) => (on ? xs.filter((x) => x !== m) : [...xs, m]))} className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-2 text-[13px] ${on ? "border-accent bg-accent-soft text-accent-strong" : "border-line bg-surface text-ink-2 hover:bg-surface-2"}`}>
                <ModalityPill m={m} />
                <span className="mono text-xs">{reqs.data?.counts?.[m] ?? 0}</span>
              </button>
            );
          })}
        </div>
        <label className="sr-only" htmlFor="req-kind">{t("req.filterKind")}</label>
        <select id="req-kind" value={kind} onChange={(e) => setKind(e.target.value)} className="h-8 rounded-md border border-line bg-surface px-2 text-[13px]">
          <option value="">{t("req.allKinds")}</option>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {t(`clauseKind.${k}`, { defaultValue: k })}
            </option>
          ))}
        </select>
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute left-2 top-2.5 text-ink-3" aria-hidden />
          <label className="sr-only" htmlFor="req-q">{t("req.search")}</label>
          <input id="req-q" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("req.search")} className="h-8 w-48 rounded-md border border-line bg-surface pl-7 pr-2 text-[13px] outline-none focus:border-accent" />
        </div>
        <label className="ml-auto inline-flex cursor-pointer items-center gap-2 text-[13px] text-interp-ink">
          <input type="checkbox" checked={plain} onChange={(e) => setPlain(e.target.checked)} className="h-4 w-4 accent-[var(--color-interp-icon)]" />
          <Lightbulb size={14} className="text-interp-icon" aria-hidden />
          {t("req.plainToggle")}
        </label>
      </div>
      {plain && plainQ.isError && (
        <p className="rounded-md bg-calm-bg px-3 py-2 text-[13px] text-calm-ink">
          {plainQ.error instanceof ApiError && plainQ.error.code === "llm_unavailable" ? t("req.plainUnavailable") : t("error.internal")}
        </p>
      )}
      {plain && plainQ.isLoading && <p className="text-[13px] text-ink-3" aria-live="polite">{t("req.plainLoading")}</p>}

      {reqs.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : reqs.isError ? (
        <ErrorState messageKey="error.internal" onRetry={() => void reqs.refetch()} />
      ) : groups.length === 0 ? (
        <p className="text-ink-3">{t("req.none")}</p>
      ) : (
        <div className="space-y-4">
          <p className="text-[13px] text-ink-3" aria-live="polite">{t("req.count", { count: reqs.data?.items.length ?? 0, clauses: groups.length })}</p>
          {groups.map((g) => (
            <section key={g.clause} className="card overflow-hidden">
              <SectionTitle>
                <span className="block px-3 pt-3 normal-case tracking-normal">
                  <Link to={clauseLink(slug, g.clause)} className="mono text-[13px] font-semibold">{g.clause}</Link>{" "}
                  <span className="text-[13px] font-medium text-ink-2">{g.heading}</span>{" "}
                  <span className="text-xs font-normal text-ink-3">· {t(`clauseKind.${g.kind}`, { defaultValue: g.kind })} · {t("evidence.page", { n: g.page })}</span>
                </span>
              </SectionTitle>
              <ul className="divide-y divide-line">
                {g.items.map((r) => (
                  <li key={r.id} className="flex gap-3 px-3 py-2.5">
                    <ModalityPill m={r.modality} />
                    <div className="min-w-0 flex-1">
                      <p className="text-[14px] leading-relaxed" lang="en">{r.text}</p>
                      {plain && plainQ.data?.items[String(r.id)] && (
                        <p className="mt-1 flex gap-1.5 rounded-md bg-interp-bg px-2 py-1 text-[13px] text-interp-ink">
                          <Lightbulb size={13} className="mt-0.5 shrink-0 text-interp-icon" aria-hidden />
                          <span>
                            <span className="font-semibold">{t("answer.interpretationShort")}: </span>
                            {plainQ.data.items[String(r.id)]}
                          </span>
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

export function RequirementsActions({ slug }: { slug: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-2">
      <a href={csvUrl(slug)} download className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink no-underline hover:bg-surface-2">
        <Download size={14} aria-hidden />
        {t("req.exportCsv")}
      </a>
      <Link to={`/standards/${slug}/checklist`} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink no-underline hover:bg-surface-2">
        <Printer size={14} aria-hidden />
        {t("req.printView")}
      </Link>
    </div>
  );
}
