# Demo script (about 4½ minutes)

Setup before judges arrive: laptop on power, `npm run demo` running, browser at http://127.0.0.1:8000,
zoom 110%, language EN, one tab. Run `npm run warm` earlier the same day (with internet) so every question
below also has a cached answer produced by the same live pipeline.

**Say up front, honestly:** "Full texts of Indian Standards need official BIS access, so the four clause-level
documents in this demo are synthetic and labelled DEMO- everywhere. Everything else — the certification,
hallmarking, lab and consumer pages and the compulsory-certification lists — is real official BIS content,
and real standards drop in through the same ingestion."

| Time | Who | Click / type | Say |
|---|---|---|---|
| 0:00 | Presenter (P6) | Home page | "MSMEs and consumers can't easily find which Indian Standard applies and what it requires. Chatbots guess. BISense answers only from an indexed library and shows the exact clause." Point at the three "Why not just ask an LLM?" points. |
| 0:20 | Driver (P4) | Click example **"What BIS standards apply to packaged drinking water?"** | "Evidence appears first, then the answer." Point at the **official BIS list row: IS 14543 — de-notified from compulsory certification**, next to the synthetic DEMO-101 specification. "Legal status comes only from an official list, never from the AI." |
| 0:50 | P4 | Type follow-up **"What are the testing requirements?"** | Point at the scope chip "Continuing with DEMO-101". Hover a citation chip → popover; click it → evidence card flashes; click **Open clause** → explorer opens at the clause, highlighted; click **View page** → original PDF page with the quote highlighted. |
| 1:40 | P4 | Explorer **Overview → "Explain this in simple language"** | "Every point cites a clause; numbers stay exact." Point at the amber **AI interpretation** box vs **From the sources**. |
| 2:00 | P4 | Home → **Compare two standards** workflow (DEMO-101 vs DEMO-102) | Scroll to **Numeric limits (verbatim)**: TDS 500 vs 150 to 700 — "copied from both tables, not computed". Point at "Not found in the indexed text" where a side is silent. |
| 2:40 | P4 | Ask **"What requirements apply to my product?"** → pick **two-wheeler helmet** | "One clarifying question, then standards with evidence." Point at **Compulsory certification (official list)** for IS 4151 citing the Helmet QCO. Open DEMO-201 → **Requirements** → **Export CSV** (and show the print checklist). "Extracted without AI; a study aid, not a certification." |
| 3:10 | P5 | Switch to **हिं**; tap the mic, say **"पैकेज्ड पेयजल के लिए कौन-से BIS मानक लागू होते हैं?"** (or click the Hindi example) | "Same pipeline: searched in English, answer translated back with standard numbers and quotes protected. 'Show original English' is one click." Optionally switch to **ಕನ್ನಡ** and click the Kannada example. |
| 3:40 | P3 | Ask **"What is the fine for selling uncertified helmets in Karnataka?"** | "It says this isn't stated in the indexed sources — no guess, and no AI call was even needed." Open **Retrieval details**: scores, the gate, removed statements. |
| 4:00 | P6 | **About** page | Pipeline diagram; **real evaluation numbers** (recall@5, refusal accuracy, false refusals) with the date; data sources with URLs and retrieval dates. |
| 4:30 | P6 | — | "Evidence first, honest refusal, official sources, three languages, runs on a laptop with free tools. Thank you." |

## If the internet or the LLM fails

- `DEMO_MODE=true` (set by `npm run demo`) tries the live LLM first, then the answer cached by `npm run warm`
  (labelled "Answer generated earlier by the same pipeline"), then verbatim clauses. Nothing needs changing on stage.
- Safe questions with cached answers: the 11 questions in `docs/demo_questions.yaml` (all of the above), the
  four "Explain in simple language" summaries, and DEMO-101 vs DEMO-102 compare.
- Fully offline still works: search, explorer, clause viewer, page images, requirements + CSV, compare
  numeric table, library, and extractive answers. Browser voice input needs internet in Chrome; typing always works.
- If an answer shows "AI summary unavailable", say: "That's the fallback — verbatim clauses, still cited."

## Likely judge questions (answers grounded in the implementation)

- **"How do you stop hallucinations?"** Three layers: the evidence gate refuses before any LLM call when no passage is relevant; the prompt allows only the numbered sources; then a deterministic validator (`server/bisense/answer/validate.py`) removes any statement whose citation, quote, number, standard number or clause reference isn't in the cited source. Removals are visible in Retrieval details. Measured drop rate and refusal accuracy are on the About page.
- **"Is this real BIS data?"** The official pages, orders and compulsory-certification lists are real (URLs and retrieval dates in `data/sources.yaml`). The four clause-level documents are synthetic because standards' full texts need official access; they're labelled on every screen, export and citation.
- **"What if the LLM is down or there's no key?"** Extractive mode: the same retrieval, verbatim clauses, clearly labelled. Demo mode also serves warmed answers.
- **"How is legal applicability decided?"** Only from indexed official lists/orders (e.g. Helmet QCO 2020 → IS 4151). "SHALL" in a standard is shown separately and never implies legal obligation.
- **"Why not fine-tune a model?"** Retrieval keeps answers traceable and updatable by re-indexing; no training data or GPU needed.
- **"How does Hindi/Kannada work?"** Query rewritten to English (identifiers protected), retrieval and validation in English, validated answer translated back; placeholders ⟦0⟧ guarantee numbers and standard numbers survive. Without an LLM, a glossary keyword map still searches.
- **"How accurate is it?"** Point to docs/EVAL.md: 62 questions, recall@5 0.98, refusal accuracy 1.0, false refusals 0.02 with Groq on 2026-09-27 — and that the demo corpus is small and partly synthetic.
- **"Cost?"** Zero: open-source components, local embeddings, free-tier or local LLM, one laptop.
- **"How would BIS deploy it?"** Point ingestion at the licensed standards collection, run the same container, keep it internal; add languages with one registry entry and one strings file.
