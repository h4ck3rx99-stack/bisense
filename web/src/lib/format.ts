// Formatting helpers for evidence labels, links and clause anchors.
import type { Citation, StandardKind } from "../api/types";

export const clauseAnchor = (number: string) => `clause-${number.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;

export const clauseLink = (slug: string, clauseNumber?: string | null) =>
  clauseNumber ? `/standards/${slug}?tab=clauses&clause=${encodeURIComponent(clauseNumber)}` : `/standards/${slug}`;

export const sourceLabel = (c: Pick<Citation, "standard_number" | "standard_title">) => c.standard_number ?? c.standard_title;

export function isWebPage(c: Pick<Citation, "doc_type" | "has_page_image">): boolean {
  return !c.has_page_image && (c.doc_type === "guidance_page" || c.doc_type === "catalogue_page");
}

export function kindKey(kind: StandardKind): string {
  return `kind.${kind}`;
}

export function shortTitle(title: string, max = 72): string {
  const t = title.replace(/\s*\(synthetic demo document, not an Indian Standard\)\s*/i, "");
  return t.length > max ? `${t.slice(0, max - 1)}…` : t;
}

/** Human label for a clause: avoids "Front Front matter" and bare word-numbers. */
export function clauseTitle(number: string, heading: string): { num: string | null; text: string } {
  if (number === "Front") return { num: null, text: heading || "Front matter" };
  if (/^[A-Za-z]/.test(number) && !/^[A-H]-\d/.test(number) && !/^(Table|Q\d)/.test(number)) {
    return { num: null, text: heading ? `${number} — ${heading}` : number };
  }
  return { num: number, text: heading };
}

/** Human citation, e.g. "Bureau of Indian Standards · IS 14543:2016 · Clause 5.2 · Page 4", with the
 *  organisation and the words Clause/Section/Page shown in the selected language (identifiers stay exact). */
export function humanSource(c: Pick<Citation, "source_label" | "source_type" | "standard_number" | "standard_title">, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (!c.source_label) return sourceLabel(c);
  const parts = c.source_label.split(" · ");
  if (c.source_type) parts[0] = t(`sourceType.${c.source_type}`);
  return parts
    .map((p) =>
      p
        .replace(/^Clause (.+)$/, (_, n) => t("cite.clause", { n }))
        .replace(/^Section (.+)$/, (_, n) => t("cite.section", { n }))
        .replace(/^Pages (\d+)–(\d+)$/, (_, a, b) => t("cite.pages", { a, b }))
        .replace(/^Page (\d+)$/, (_, n) => t("cite.page", { n })),
    )
    .join(" · ");
}
