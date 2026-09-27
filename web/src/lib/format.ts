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
