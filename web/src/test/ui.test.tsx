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
  retry_after_s: null,
  searched_summary: "",
  library_note: "",
  coverage: [],
  verdict: null,
  suggestions: [],
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
    const order = ["Short answer", "Key points, from the source", "What this means for you", "Next step"];
    const idx = order.map((h) => headings.indexOf(h));
    expect(idx.every((i) => i >= 0)).toBe(true);
    expect([...idx].sort((a, b) => a - b)).toEqual(idx);
    expect(screen.getByText(/Explanation written by BISense \(AI interpretation\)/)).toBeInTheDocument();
    expect(screen.getAllByText("Sample data, not official").length).toBeGreaterThan(0);
    expect(container.textContent).not.toMatch(/\bC1\b|rerank|fused/);
  });

  it("shows the human citation under 'See the original text'", async () => {
    wrap(<AnswerBlock answer={answer} citations={new Map([["C1", citation]])} />);
    await userEvent.click(screen.getAllByRole("button", { name: "See the original text" })[0]);
    expect(screen.getByText("Sample data, not official · DEMO-101:2026 · Clause 4.3.1 · Page 2")).toBeInTheDocument();
  });

  it("leads with the verdict card and keeps proof behind one button", async () => {
    const listRow: Citation = {
      ...citation,
      id: "C1",
      clause_kind: "list",
      snippet: "Product: Helmet for riders of Two Wheeler Motor Vehicles · IS 4151: 2015 · Scheme-I ISI mark · Order: 65. Helmet (Quality Control) Order, 2020 (S.O. No. 4252 (E) 26/11/2020)",
      synthetic: false,
      source_type: "official_website",
      text_scope: "page",
      url: "https://www.bis.gov.in/x",
    };
    const verdictAnswer: Answer = {
      ...answer,
      synthetic_used: false,
      points: [{ kind: "source_fact", text: "Helmet for riders of Two Wheeler Motor Vehicles · IS 4151: 2015 · Scheme-I ISI mark · Order: 65. S.O. No. 4252 (E)", citations: ["C1"], quote: null }],
      verdict: {
        kind: "compulsory",
        possible: false,
        product: "Helmet for riders of Two Wheeler Motor Vehicles",
        standard_slug: "is-4151-2015",
        standard_number: "IS 4151:2015",
        standard_title: "Protective Helmet for Two Wheeler Riders",
        scheme: "ISI",
        order_short: "Helmet for riders of Two Wheeler Motor Vehicles QCO 2020",
        denotified: false,
        source: { label: "Official BIS website · Products under Compulsory Certification", url: "https://www.bis.gov.in/x", citation_id: "C1", page: null, source_type: "official_website" },
      },
    };
    let open = false;
    const { rerender, container } = wrap(<AnswerBlock answer={verdictAnswer} citations={new Map([["C1", listRow]])} proofOpen={open} onToggleProof={() => (open = !open)} />);
    expect(screen.getByRole("heading", { name: "Yes — BIS certification is compulsory for Helmet for riders of Two Wheeler Motor Vehicles" })).toBeInTheDocument();
    expect(screen.getByTestId("standard-chip")).toHaveAttribute("href", "/standards/is-4151-2015");
    expect(container.querySelectorAll("ol li")).toHaveLength(3);
    expect(screen.getByTestId("verdict-source")).toHaveTextContent("Official BIS list of products under compulsory certification");
    // raw notification text and the evidence stay behind "Show proof and details"
    expect(container.textContent).not.toMatch(/S\.O\. No\./);
    expect(screen.queryByTestId("proof")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show proof and details" }));
    expect(open).toBe(true);
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ToastProvider>
          <MemoryRouter>
            <AnswerBlock answer={verdictAnswer} citations={new Map([["C1", listRow]])} proofOpen onToggleProof={() => {}} />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("proof")).toHaveTextContent(/S\.O\. No\. 4252/);
  });

  it("not found: plain message, two rephrasings that ask again, and the step-by-step finder", async () => {
    const asked: string[] = [];
    const notFound: Answer = { ...answer, answer_type: "insufficient_evidence", points: [], summary: "", verdict: { kind: "not_found", possible: false, product: null, standard_slug: null, standard_number: null, standard_title: null, scheme: null, order_short: null, denotified: false, source: null }, suggestions: ["Is BIS certification compulsory for Cotton Bales?", "Is BIS certification compulsory for my product?"] };
    const { container } = wrap(<AnswerBlock answer={notFound} citations={new Map()} onFollowUp={(q) => asked.push(q)} />);
    expect(screen.getByText("We couldn't find this in official BIS sources")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/Searched \d+/);
    await userEvent.click(screen.getByRole("button", { name: "Is BIS certification compulsory for my product?" }));
    expect(asked).toEqual(["Is BIS certification compulsory for my product?"]);
    expect(screen.getByRole("link", { name: /Find standards step by step/ })).toHaveAttribute("href", "/guide");
  });

  it("keeps the exact source wording collapsed until asked for", async () => {
    const quoted: Answer = { ...answer, points: [{ kind: "source_fact", text: "Coliform must be absent.", citations: ["C1"], quote: "shall be absent in any 250 ml sample" }] };
    wrap(<AnswerBlock answer={quoted} citations={new Map([["C1", citation]])} />);
    expect(screen.queryByText(/shall be absent in any 250 ml sample/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "See the original text" }));
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
