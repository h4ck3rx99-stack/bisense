# Demo script (about 4½ minutes)

**Before judges arrive (same day, with internet):** `npm run fetch-public`, `npm run ingest`, `npm run warm`
(runs every question below through the real pipeline and caches the validated result), then `npm run demo`.
Browser at http://127.0.0.1:8000, zoom 110 %, language EN, one tab. For a phone demo, serve over HTTPS
(README → "Serving over HTTPS"), otherwise the microphone is blocked.

Data mode is **official** (`DATASET=official`): every source on screen is an official BIS document, BIS web
page or government notification. Say it once: "Full texts of Indian Standards need a BIS account, so for
most standards BISense has the official product manual or the official list entry — and it tells you which."

| Time | Who | Do | Say |
|---|---|---|---|
| 0:00 | Presenter | Home page | "If you make, sell or buy a product in India, which BIS standard applies, and what does it ask? BISense answers in plain words and shows the official source for every fact." Point at the coverage line: "It says exactly how much it covers." |
| 0:20 | Driver | Tap **Find standards for my product** → **Standards for a product** → type **plastic food containers** → **Find** (J1, J5) | "No BIS words needed." Short answer, key points, then the relevant standards as cards with plain titles first (IS 10910, IS 17569 …). Tap **Sources**: "Bureau of Indian Standards · Product Manual for IS … · Page …". |
| 1:00 | Driver | Tap a key point's **Exact wording and source** → tap citation **1** | "Beginners see a short statement; the exact source sentence is one tap away, highlighted." Evidence card → **Open clause** / **View page** (original page, sentence highlighted). |
| 1:30 | Driver | Home → example **Is BIS certification compulsory for two-wheeler helmets?** (J2) | "Legal status comes only from the official list and the Helmet Quality Control Order — never from the AI." Point at the badge and its source. |
| 1:50 | Driver | Next step **Explain simply** (J3), then type **What are the important requirements?** (J4) | The "About: IS 4151:2015" chip shows the follow-up kept its standard. Point at the amber **What this means for you — explanation written by BISense (AI interpretation)**, separate from the key points "from the source". |
| 2:30 | Second speaker | Next step **Ask in हिंदी**, or switch to **ಕನ್ನಡ** and tap the mic: "ಹೆಲ್ಮೆಟ್‌ಗೆ ಯಾವ ಮಾನದಂಡ ಇದೆ?" | "One language setting drives the screen, the microphone and the answer. Standard numbers and quotes are protected during translation; the source wording stays original." Tap the speaker for read-aloud (English server voice; Hindi/Kannada if the device has a voice — it says so if not). |
| 3:10 | Third speaker | Ask **What is the fine for selling uncertified helmets in Karnataka?** (J6) | "It says this isn't in the BIS sources it has, and suggests what to try — no guess, no AI call." |
| 3:30 | Driver | Standard page **IS 4151** → **At a glance** → **Related & compare** → **Compare with another standard** → IS 2925 (J7) | "Experts still get everything: exact numbers, clauses, verbatim evidence, comparison." On an answer open **Retrieval details**: interpreted query, passages with scores, which were cited, removed statements, timings, live/cached/evidence-only. |
| 4:10 | Presenter | About page | Data sources with URLs and retrieval dates; evaluation numbers with their date. "Official sources, honest refusals, three languages, runs on one laptop with free tools." |

## If the internet or a provider fails

- `npm run demo` sets `DEMO_MODE=true`: live LLM first, then the answer cached by `npm run warm` (labelled
  "Answer generated earlier by the same pipeline"), then the evidence-only answer ("AI summary unavailable
  right now; here is what the sources say"). Nothing needs changing on stage.
- Works fully offline once set up: search, guided path, standard pages, clauses, page images, requirements +
  CSV, compare table, evidence-only answers, Hindi/Kannada questions (glossary keyword fallback), read-aloud
  where the device has voices.
- Needs internet: the LLM (summaries, translation of answers), server speech-to-text and server voice.
  Without them the mic falls back to the browser's recognition (Chrome/Edge) and typing always works.
- If the reranker model was never downloaded, `/api/health` says so and search still works (slightly
  weaker ranking). Run `npm run setup` once with internet to fix it.

## Likely judge questions (answers grounded in the implementation)

- **"Is this real BIS data?"** Yes by default: bis.gov.in pages, the compulsory-certification lists, 12 official product manuals, and Quality Control Orders, each with URL and retrieval date (`data/public/fetch_log.yaml`). Sample data exists only for development, is off by default, and is labelled "Sample data, not official" everywhere when switched on.
- **"How do you stop hallucinations?"** The evidence gate refuses before any AI call when nothing relevant is found; the prompt sees only numbered sources; a deterministic validator (`server/bisense/answer/validate.py`) removes any statement whose citation, quote, number or standard number is not in the cited source. `tests/test_rag_proof.py` proves it: remove a document and the fact disappears even from a model that "knows" it.
- **"What if the AI is down?"** Evidence-only answers from the same retrieval, clearly labelled; demo mode also serves warmed answers.
- **"How is compulsory certification decided?"** Only from the official lists and orders. "Shall" in a standard is shown separately and never implies a legal obligation.
- **"How do Hindi and Kannada work?"** The question is turned into English for searching (identifiers protected), the validated answer is translated back with placeholders so numbers and standard numbers survive; quoted source text stays original with an optional translation. Without an AI key a glossary keyword map still searches.
- **"Does the microphone really work?"** Audio is recorded in the browser and sent to the server (keys never reach the browser) for Whisper transcription in English, Hindi and Kannada; the transcript lands in the box for correction. Tested with a fake microphone in Chrome and real audio fixtures.
- **"Accuracy?"** docs/EVAL.md: the question set, the date, the model and the numbers, including refusal accuracy and false refusals.
- **"Cost?"** Zero: open-source components, local search models, free-tier or local LLM, one laptop.
