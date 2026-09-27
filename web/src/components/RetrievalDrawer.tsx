// "Retrieval details" drawer: makes the pipeline auditable (query interpretation, candidates with
// lexical/semantic/rerank scores, which were cited, validation drops, mode and timings).
import * as Dialog from "@radix-ui/react-dialog";
import { useTranslation } from "react-i18next";
import { Microscope, X } from "lucide-react";
import type { AskTrace } from "../api/types";
import { sourceLabel } from "../lib/format";
import { Badge } from "./ui";

export function RetrievalDrawer({ trace }: { trace: AskTrace | null }) {
  const { t } = useTranslation();
  if (!trace) return null;
  const cited = new Set(trace.cited_ids);
  return (
    <Dialog.Root>
      <Dialog.Trigger className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 text-[13px] font-medium text-ink-2 hover:bg-surface-2">
        <Microscope size={14} aria-hidden />
        {t("trace.open")}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[rgb(20_20_30/0.35)]" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[680px] flex-col bg-surface shadow-[var(--shadow-pop)]">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <Dialog.Title className="text-[16px] font-semibold">{t("trace.title")}</Dialog.Title>
            <Dialog.Close className="rounded-md p-2 hover:bg-surface-2" aria-label={t("action.close")}>
              <X size={18} aria-hidden />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">{t("trace.description")}</Dialog.Description>
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4 text-[13px]">
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-ink-3">{t("trace.interpreted")}</dt>
              <dd lang="en">{trace.query.interpreted_query}</dd>
              <dt className="text-ink-3">{t("trace.intent")}</dt>
              <dd className="mono">{trace.query.intent}</dd>
              <dt className="text-ink-3">{t("trace.language")}</dt>
              <dd className="mono">{trace.query.lang}{trace.query.rewritten ? ` · ${t("trace.rewritten")}` : ""}</dd>
              <dt className="text-ink-3">{t("trace.scope")}</dt>
              <dd>{trace.query.resolved_scope.map((s) => s.number ?? s.title).join(", ") || "—"} <span className="text-ink-3">({trace.query.scope_source})</span></dd>
              <dt className="text-ink-3">{t("trace.mode")}</dt>
              <dd>
                <Badge tone={trace.mode === "live" ? "ok" : "calm"}>{t(`mode.${trace.mode}`)}</Badge> {trace.provider && <span className="mono text-ink-3">{trace.provider}</span>}
              </dd>
              <dt className="text-ink-3">{t("trace.gate")}</dt>
              <dd className="mono">{trace.top_rerank !== null && trace.top_rerank !== undefined ? `${trace.top_rerank.toFixed(2)} ≥ ${trace.gate_threshold}` : t("trace.noRerank")}</dd>
              <dt className="text-ink-3">{t("trace.total")}</dt>
              <dd className="mono">{Math.round(trace.timings.total_ms)} ms</dd>
              {trace.query.notes.length > 0 && (
                <>
                  <dt className="text-ink-3">{t("trace.notes")}</dt>
                  <dd>{trace.query.notes.join("; ")}</dd>
                </>
              )}
            </dl>

            <section>
              <h3 className="mb-1.5 font-semibold">{t("trace.timings")}</h3>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(trace.timings.stages).map(([k, v]) => (
                  <span key={k} className="mono rounded-sm bg-surface-2 px-1.5 py-0.5 text-xs">
                    {k} {Math.round(v)}ms
                  </span>
                ))}
              </div>
            </section>

            <section>
              <h3 className="mb-1.5 font-semibold">{t("trace.candidates")}</h3>
              <div className="overflow-x-auto rounded-md border border-line">
                <table className="w-full text-xs">
                  <thead className="bg-surface-2 text-left">
                    <tr>
                      <th className="px-2 py-1.5">#</th>
                      <th className="px-2 py-1.5">{t("trace.source")}</th>
                      <th className="px-2 py-1.5 text-right">{t("trace.lexical")}</th>
                      <th className="px-2 py-1.5 text-right">{t("trace.semantic")}</th>
                      <th className="px-2 py-1.5 text-right">{t("trace.rerank")}</th>
                      <th className="px-2 py-1.5">{t("trace.cited")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trace.candidates.map((c) => (
                      <tr key={`${c.slug}-${c.clause_number}-${c.n}`} className="border-t border-line align-top">
                        <td className="mono px-2 py-1.5">{c.n}</td>
                        <td className="px-2 py-1.5">
                          <span className="mono font-medium">{sourceLabel(c)}</span> <span className="mono text-ink-3">{c.clause_number}</span>
                        </td>
                        <td className="mono px-2 py-1.5 text-right">{c.scores.lexical_rank ?? "—"}</td>
                        <td className="mono px-2 py-1.5 text-right">{c.scores.vector?.toFixed(3) ?? "—"}</td>
                        <td className="mono px-2 py-1.5 text-right">{c.scores.rerank?.toFixed(2) ?? "—"}</td>
                        <td className="px-2 py-1.5">{c.id.startsWith("C") && cited.has(c.id) ? <Badge tone="ok">{c.id}</Badge> : c.id.startsWith("C") ? <span className="mono text-ink-3">{c.id}</span> : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h3 className="mb-1.5 font-semibold">{t("trace.drops", { count: trace.drops.length })}</h3>
              {trace.drops.length === 0 ? (
                <p className="text-ink-3">{t("trace.noDrops")}</p>
              ) : (
                <ul className="space-y-1.5">
                  {trace.drops.map((d, i) => (
                    <li key={i} className="rounded-md bg-surface-2 p-2">
                      <span className="mono text-xs text-ink-3">{d.field}</span> — {d.reason}
                      <div className="mt-0.5 text-ink-3" lang="en">“{d.text}”</div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
