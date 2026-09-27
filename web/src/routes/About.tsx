// /about — problem, why not just an LLM, how it works, data provenance, REAL eval numbers, limitations.
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ExternalLink } from "lucide-react";
import { api } from "../api/client";
import { useLibrary } from "../lib/hooks";
import { Badge, SectionTitle, Skeleton } from "../components/ui";
import team from "../team.json";

const PIPELINE = ["understand", "retrieve", "fuse", "rerank", "gate", "generate", "validate", "translate", "show"] as const;

export default function About() {
  const { t } = useTranslation();
  const library = useLibrary();
  const ev = useQuery({ queryKey: ["eval"], queryFn: api.eval, staleTime: 300_000 });
  const sources = library.data?.sources ?? [];
  const byTier = (tier: string) => sources.filter((s) => s.tier === tier);

  return (
    <div className="mx-auto max-w-4xl space-y-10">
      <header>
        <h1 className="text-3xl font-semibold">{t("about.title")}</h1>
        <p className="mt-2 text-[16px] text-ink-2">{t("about.lead")}</p>
      </header>

      <section aria-labelledby="ab-problem">
        <SectionTitle id="ab-problem">{t("about.problemTitle")}</SectionTitle>
        <p className="text-[15px] leading-relaxed">{t("about.problem")}</p>
      </section>

      <section aria-labelledby="ab-why">
        <SectionTitle id="ab-why">{t("why.title")}</SectionTitle>
        <ol className="grid gap-3 sm:grid-cols-2">
          {["cite", "refuse", "separate", "extract", "multilingual", "inspect"].map((k, i) => (
            <li key={k} className="card p-3.5">
              <div className="mono text-xs text-ink-3">{String(i + 1).padStart(2, "0")}</div>
              <div className="font-semibold">{t(`why.${k}.title`)}</div>
              <div className="text-[14px] text-ink-2">{t(`why.${k}.body`)}</div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="ab-how">
        <SectionTitle id="ab-how">{t("about.howTitle")}</SectionTitle>
        <ol className="flex flex-wrap items-center gap-1.5" aria-label={t("about.pipelineLabel")}>
          {PIPELINE.map((s, i) => (
            <li key={s} className="flex items-center gap-1.5">
              <span className={`rounded-md border px-2.5 py-1.5 text-[13px] font-medium ${s === "validate" || s === "gate" ? "border-accent bg-accent-soft text-accent-strong" : "border-line bg-surface"}`}>{t(`about.pipeline.${s}`)}</span>
              {i < PIPELINE.length - 1 && <ArrowRight size={14} className="text-ink-3" aria-hidden />}
            </li>
          ))}
        </ol>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-[14px] text-ink-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <li key={n}>{t(`about.how${n}`)}</li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="ab-eval">
        <SectionTitle id="ab-eval">{t("about.evalTitle")}</SectionTitle>
        {ev.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : !ev.data?.available ? (
          <p className="text-ink-3">{t("about.evalMissing")}</p>
        ) : (
          <div className="space-y-2">
            <p className="text-[13px] text-ink-3">
              {t("about.evalMeta", { date: ev.data.generated_at?.slice(0, 10), mode: ev.data.dataset_mode, n: ev.data.counts?.questions ?? 0, llm: ev.data.llm ?? t("about.evalNoLlm") })}
            </p>
            <div className="grid gap-2 sm:grid-cols-3">
              {Object.entries(ev.data.metrics ?? {})
                .filter(([, v]) => v !== null && v !== undefined)
                .map(([k, v]) => {
                  const target = ev.data?.targets?.[k];
                  return (
                    <div key={k} className="card p-3">
                      <div className="text-xs text-ink-3">{t(`about.metric.${k}`, { defaultValue: k })}</div>
                      <div className="mono text-xl font-semibold">{typeof v === "number" ? (k.includes("ms") ? `${Math.round(v)} ms` : v.toFixed(2)) : String(v)}</div>
                      {target !== undefined && <div className="text-xs text-ink-3">{t("about.target", { v: target })}</div>}
                    </div>
                  );
                })}
            </div>
            <p className="text-xs text-ink-3">{t("about.evalNote")}</p>
          </div>
        )}
      </section>

      <section aria-labelledby="ab-data" id="data">
        <SectionTitle id="ab-data">{t("about.dataTitle")}</SectionTitle>
        <p className="mb-3 text-[14px] text-ink-2">{t("about.dataIntro")}</p>
        {(["A", "B", "C"] as const).map((tier) => {
          const items = byTier(tier);
          return (
            <div key={tier} className="mb-4">
              <h3 className="mb-1 flex items-center gap-2 text-[15px] font-semibold">
                {t(`tier.${tier}`)} <Badge tone={tier === "C" ? "synth" : "neutral"}>{items.length}</Badge>
              </h3>
              <p className="mb-1.5 text-[13px] text-ink-3">{t(`about.tier${tier}`)}</p>
              {items.length > 0 && (
                <ul className="card max-h-64 divide-y divide-line overflow-y-auto text-[13px]">
                  {items.map((s) => (
                    <li key={s.file} className="flex items-baseline justify-between gap-3 px-3 py-2">
                      <span className="min-w-0">
                        <span className="block truncate">{s.title}</span>
                        {s.obtained_on && <span className="text-xs text-ink-3">{t("standard.obtainedOn", { date: s.obtained_on })}</span>}
                      </span>
                      {s.url && (
                        <a href={s.url} target="_blank" rel="noopener noreferrer" className="shrink-0" aria-label={t("about.openSource", { title: s.title })}>
                          <ExternalLink size={14} aria-hidden />
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </section>

      <section aria-labelledby="ab-limits">
        <SectionTitle id="ab-limits">{t("about.limitsTitle")}</SectionTitle>
        <ul className="list-disc space-y-1 pl-5 text-[14px] text-ink-2">
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <li key={n}>{t(`about.limit${n}`)}</li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="ab-disc" className="rounded-lg border border-line-strong bg-surface p-4">
        <h2 id="ab-disc" className="mb-1 font-semibold">{t("about.disclaimerTitle")}</h2>
        <p className="text-[14px]">{t("footer.disclaimer")}</p>
      </section>

      <section aria-labelledby="ab-team">
        <SectionTitle id="ab-team">{t("about.teamTitle")}</SectionTitle>
        <p className="text-[14px]">
          <span className="font-semibold">{team.name}</span> · {team.event}
        </p>
        {team.members.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-2 text-[14px]">
            {(team.members as { name: string; role?: string }[]).map((m) => (
              <li key={m.name} className="card px-3 py-1.5">
                {m.name}
                {m.role ? <span className="text-ink-3"> · {m.role}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
