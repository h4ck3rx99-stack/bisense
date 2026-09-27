# Plan and requirement traceability

Official requirements come from `docs/PROBLEM_STATEMENT.md` (SIH26107, retrieved 2026-09-27 from
sih.gov.in). The official text decides WHAT to build; the build brief decides HOW (evidence-first).

## Traceability

| Official expected outcome | BISense feature | Evidence source in the library |
|---|---|---|
| Answer questions related to Indian Standards | Ask (/ask), explorer "Ask about this standard", clause lookup, definitions | Full-text standards (Tier A when added; Tier C demo pack now) |
| Recommend applicable standards based on product descriptions | Discover intent + product probe over official BIS "Products under Compulsory Certification" lists; applicability flow with one clarifying question | Scheme-I / Scheme-II lists (Tier B, 924 product→IS mappings) + standard scopes |
| Provide guidance on BIS certification schemes | Ask over indexed BIS pages: Product Certification FAQ, FMCS, Scheme-X, compulsory registration; QCO PDFs | Tier B official pages and orders |
| Explain certification processes | Ask + explorer on "Guidelines for Grant of Licence (Scheme-I)" (62-page official PDF) | Tier B |
| Answer consumer-related queries | Ask over consumer FAQ, complaint registration, consumer protection pages | Tier B |
| Guide users regarding hallmarking | Ask over hallmarking overview, FAQs, consumer FAQ, mandatory hallmarking order, AHC pages | Tier B |
| Suggest relevant testing laboratories | Ask over BIS laboratory pages (list of BIS labs, lab FAQ, recognition, MSME cluster-lab guidelines) | Tier B |
| Support multilingual interaction | EN / हिं / ಕನ್ನಡ UI; Hindi/Kannada queries (typed or voice) with English-pivot retrieval, validated answers translated back with protected numbers | i18n registry + glossary |
| "Source-backed ... with references to documents or clauses" | Every statement cites standard, clause and page; validator drops unsupported claims; honest refusal | Validator + gate |

## Priorities and time boxes

MUST (done first, no time box): ingestion + demo pack, hybrid retrieval, validated answers, refusal,
extractive fallback, follow-up context, library/explorer/clause viewer, citation→clause, summaries,
requirements, compare, en/hi/kn, responsive UI, demo mode/cache/doctor, README, `npm run check`.

SHOULD (time-boxed, ~1–2 h each): checklist export + print view, applicability flow, browser voice,
page preview with highlight, Retrieval details drawer, typeahead + filters, numeric-limits alignment,
About page with real eval numbers.

COULD (only if everything else is solid): server STT/TTS providers, uploads, reference graph, dark mode,
cloud deploy.
