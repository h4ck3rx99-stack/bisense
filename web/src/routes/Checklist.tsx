// /standards/:slug/checklist — print-optimised requirements checklist (study aid, not a compliance determination).
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Printer } from "lucide-react";
import { api } from "../api/client";
import { Button, ErrorState, Skeleton, SyntheticBadge } from "../components/ui";
import { groupByClause, ModalityPill } from "./Requirements";

export default function Checklist() {
  const { slug = "" } = useParams();
  const { t } = useTranslation();
  const reqs = useQuery({ queryKey: ["req", slug, "", "", ""], queryFn: () => api.requirements(slug, {}) });
  const groups = useMemo(() => groupByClause(reqs.data?.items ?? []), [reqs.data]);
  if (reqs.isLoading) return <Skeleton className="h-64 w-full" />;
  if (reqs.isError || !reqs.data) return <ErrorState messageKey="error.not_found" />;
  const d = reqs.data;
  const label = d.number ?? d.title;
  return (
    <div className="mx-auto max-w-4xl">
      <div className="no-print mb-4 flex items-center justify-between gap-2">
        <Link to={`/standards/${slug}?tab=requirements`} className="inline-flex items-center gap-1 text-[14px]">
          <ArrowLeft size={15} aria-hidden />
          {t("checklist.back")}
        </Link>
        <Button variant="primary" onClick={() => window.print()}>
          <Printer size={15} aria-hidden />
          {t("checklist.print")}
        </Button>
      </div>
      <header className="mb-4 border-b border-line pb-3">
        <h1 className="text-xl font-semibold">
          {t("checklist.title")}: <span className="mono">{label}</span>
        </h1>
        {d.number && <p className="text-[14px] text-ink-2">{d.title}</p>}
        <p className="mt-2 text-[13px] text-ink-2">{t("req.header", { label })}</p>
        {d.synthetic && (
          <div className="mt-2">
            <SyntheticBadge />
          </div>
        )}
        <p className="mt-2 text-xs text-ink-3">{t("checklist.generated", { date: new Date().toLocaleDateString() })}</p>
      </header>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b-2 border-ink text-left">
            <th scope="col" className="w-8 py-1.5">✓</th>
            <th scope="col" className="w-20 py-1.5">{t("checklist.clause")}</th>
            <th scope="col" className="w-24 py-1.5">{t("checklist.modality")}</th>
            <th scope="col" className="py-1.5">{t("checklist.requirement")}</th>
            <th scope="col" className="w-28 py-1.5">{t("checklist.notes")}</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) =>
            g.items.map((r, i) => (
              <tr key={r.id} className="break-inside-avoid border-b border-line align-top">
                <td className="py-2">
                  <span className="inline-block h-4 w-4 rounded-sm border border-ink-3" aria-hidden />
                </td>
                <td className="mono py-2">{i === 0 ? g.clause : ""}</td>
                <td className="py-2">
                  <ModalityPill m={r.modality} />
                </td>
                <td className="py-2 pr-3" lang="en">
                  {r.text} <span className="text-ink-3">(p. {r.page})</span>
                </td>
                <td className="py-2" />
              </tr>
            )),
          )}
        </tbody>
      </table>
      <p className="mt-4 text-xs text-ink-3">{t("footer.disclaimer")}</p>
    </div>
  );
}
