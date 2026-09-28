import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import en from "../i18n/en.json";
import hi from "../i18n/hi.json";
import kn from "../i18n/kn.json";
import "../i18n";
import { Markdown } from "../components/Markdown";
import { AnswerBlock, quoteRepeatsText } from "../components/Answer";
import { CitationChip } from "../components/Evidence";
import { ToastProvider } from "../components/Toast";
import { parseSSE } from "../api/sse";
import { normalizeSpokenNumbers } from "../lib/speech";
import type { Answer, Citation } from "../api/types";

function flat(o: Record<string, unknown>, p = ""): string[] {
  return Object.entries(o).flatMap(([k, v]) => (v && typeof v === "object" ? flat(v as Record<string, unknown>, p + k + ".") : [p + k]));
}

function wrap(ui: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ToastProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const citation: Citation = {
  id: "C1",
  n: 1,
  slug: "demo-101-2026",
  standard_number: "DEMO-101:2026",
  standard_title: "Illustrative Packaged Drinking Water Specification",
  standard_kind: "standard",
  clause_number: "4.3.1",
  clause_heading: "",
  clause_kind: "requirement",
  clause_path: "4 Requirements › 4.3.1",
  page_start: 2,
  page_end: 2,
  snippet: "Coliform bacteria shall be absent in any 250 ml sample of the water.",
  scores: { lexical_rank: 1, vector: 0.8, fused: 0.03, rerank: 5.1, boosts: {} },
  synthetic: true,
  tier: "D",
  doc_type: "synthetic_demo",
  url: null,
  has_page_image: true,
  text_scope: "sample",
  document_title: "Illustrative Packaged Drinking Water Specification",
  source_org: "BISense sample data (not official)",
  source_type: "sample",
  source_label: "Sample data, not official · DEMO-101:2026 · Clause 4.3.1 · Page 2",
};

const answer: Answer = {
  answer_type: "answer",
  summary: "Coliform bacteria must be absent [C1].",
  points: [
    { kind: "source_fact", text: "Coliform bacteria shall be absent in any 250 ml sample.", citations: ["C1"], quote: null },
    { kind: "interpretation", text: "In practice every bottle must test negative.", citations: ["C1"], quote: null },
  ],
  standards: [],
  gaps: [],
  clarifying_question: null,
  clarifying_options: [],
  follow_ups: [],
  evidence_strength: "strong",
  strength_basis: "Cites 1 passage.",
  mode: "live",
  provider: "fake",
  generated_at: null,
  dropped_count: 0,
  drops: [],
  lang: "en",
  translated: false,
  translation_failed: false,
  original: null,
  notice: null,
  searched_summary: "",
  library_note: "",
  coverage: [],
  synthetic_used: true,
};

describe("i18n", () => {
  it("has the same keys in every language", () => {
    const base = flat(en).sort();
    expect(flat(hi).sort()).toEqual(base);
    expect(flat(kn).sort()).toEqual(base);
  });
});

describe("Markdown", () => {
  it("never renders raw HTML from sources", () => {
    const { container } = render(<Markdown text={'<img src=x onerror="alert(1)"><script>alert(2)</script> safe **bold**'} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.innerHTML).not.toContain("onerror");
    expect(container.querySelector("strong")?.textContent).toBe("bold");
  });
  it("renders tables", () => {
    const { container } = render(<Markdown text={"| a | b |\n|---|---|\n| 1 | 2 |"} />);
    expect(container.querySelectorAll("td")).toHaveLength(2);
  });
});

describe("Answer rendering", () => {
  it("renders the beginner structure in order, keeping source facts apart from the AI explanation", () => {
    const { container } = wrap(<AnswerBlock answer={answer} citations={new Map([["C1", citation]])} onFollowUp={() => {}} onAskIn={() => {}} />);
    const headings = [...container.querySelectorAll("h2, h3")].map((h) => h.textContent);
    const order = ["Short answer", "Key points, from the source", "What this means for you", "Sources", "Next step"];
    const idx = order.map((h) => headings.indexOf(h));
    expect(idx.every((i) => i >= 0)).toBe(true);
    expect([...idx].sort((a, b) => a - b)).toEqual(idx);
    expect(screen.getByText(/Explanation written by BISense \(AI interpretation\)/)).toBeInTheDocument();
    expect(screen.getAllByText("Sample data, not official").length).toBeGreaterThan(0);
    // human citation, no internal ids or scores
    expect(screen.getByText("Sample data, not official · DEMO-101:2026 · Clause 4.3.1 · Page 2")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\bC1\b|rerank|fused/);
  });

  it("keeps the exact source wording collapsed until asked for", async () => {
    const quoted: Answer = { ...answer, points: [{ kind: "source_fact", text: "Coliform must be absent.", citations: ["C1"], quote: "shall be absent in any 250 ml sample" }] };
    wrap(<AnswerBlock answer={quoted} citations={new Map([["C1", citation]])} />);
    expect(screen.queryByText(/shall be absent in any 250 ml sample/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Exact wording and source" }));
    expect(screen.getByText(/shall be absent in any 250 ml sample/)).toBeInTheDocument();
  });

  it("citation chips name their source for screen readers and open a popover on focus", async () => {
    wrap(<CitationChip id="C1" citations={new Map([["C1", citation]])} />);
    const chip = screen.getByRole("button", { name: /Source 1: DEMO-101:2026, clause 4.3.1/ });
    await userEvent.tab();
    expect(chip).toHaveFocus();
    expect(await screen.findByText(/250 ml sample/)).toBeInTheDocument();
  });

  it("drops chips for unknown citation ids", () => {
    const { container } = wrap(<CitationChip id="C9" citations={new Map([["C1", citation]])} />);
    expect(container.querySelector("button")).toBeNull();
  });

  it("hides a quote that only repeats the statement", () => {
    expect(quoteRepeatsText("Coliform bacteria shall be absent", "Coliform bacteria shall be absent.")).toBe(true);
    expect(quoteRepeatsText("500 mg/l", "The limit for total dissolved solids in packaged water is 500 mg/l per Table 1.")).toBe(false);
  });
});

describe("helpers", () => {
  it("parses SSE blocks", () => {
    const evs = parseSSE('event: stage\ndata: {"stage":"searching"}\n\nevent: done\ndata: {"request_id":"x"}\n\n');
    expect(evs.map((e) => e.event)).toEqual(["stage", "done"]);
    expect(JSON.parse(evs[0].data).stage).toBe("searching");
  });
  it("normalises spoken standard numbers", () => {
    expect(normalizeSpokenNumbers("I S fourteen five four three for water")).toBe("IS 14543 for water");
    expect(normalizeSpokenNumbers("is one seven eight six")).toBe("IS 1786");
    expect(normalizeSpokenNumbers("the pH is 7")).toBe("the pH is 7");
    expect(normalizeSpokenNumbers("the limit is 10 mg")).toBe("the limit is 10 mg");
    expect(normalizeSpokenNumbers("IS fourteen five forty three")).toBe("IS 14543");
    expect(normalizeSpokenNumbers("I S three zero two")).toBe("IS 302");
  });
});
