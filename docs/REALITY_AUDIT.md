# Reality audit

Started 2026-09-28 for the "repair, verify and redesign" pass. One row per feature. Status: Working / Partial /
Broken / Fake / Dead. Decision: keep / fix / rewrite / remove. "Evidence" is what was run or read, not a claim.
Rows are updated as fixes land (see the "After" column).

| Feature | Files | What it claims | Status (before) | Evidence | Root cause | Decision | After |
|---|---|---|---|---|---|---|---|
| Search / retrieval | `server/bisense/retrieval/*` | Hybrid BM25 + embeddings + RRF + reranker | Working | Eval 62 q: recall@5 1.00, exact hit 1.00 (docs/EVAL.md); `bisense search --explain` | — | keep | Kept. Pass 2: reranker failure no longer crashes search; topic boost for marking/packing/sampling questions (`--explain`: marking clauses 5/9 → 1/2). |
| AI answers (RAG) | `answer/ask.py`, `generate.py` | Answers only from retrieved passages | Working | LLM receives only `<sources>` blocks; validator; eval refusal 1.00 | — | keep; add known-answer / ablation proof tests | Proof tests added: `test_rag_proof.py` (official, pass 1) + `test_rag_mechanism.py` (sample, runs everywhere). Evidence-only answers drop weak passages. |
| Citations | `answer/validate.py`, `components/Evidence.tsx` | Citations tied to retrieved chunks | Working but expert-styled | Citation ids validated against context; UI shows `[n]` chips + raw clause numbers | Designed for experts; no human-format label, scores visible in cards | fix (human citation format; scores only in expert panel) | Fixed: human citations from provenance (`source_label`, localised), source badges, Sources section; scores only in Retrieval details (vitest asserts none in the answer). |
| **Default data** | `ingest/manifest.py`, `data/demo` | Official data | **Partial / misleading by default** | `DATASET=auto` loads the synthetic DEMO pack whenever no Tier A PDFs exist; the only clause-level "standards" are synthetic | Earlier design treated synthetic data as a default fallback | **rewrite**: official-only by default; synthetic = opt-in sample mode | Fixed (pass 1): `DATASET=official` default; sample pack only with `DATASET=sample`, labelled "Sample data, not official". Pass 2: sample banner bug fixed (`demo` → `sample`). |
| Official data | `data/public_sources.yaml` | BIS pages, lists, QCOs | Working | 32 official files with URL + date in `data/public/fetch_log.yaml` | — | keep; add official product manuals + department listings | Kept + 12 official product manuals (pass 1). Not re-fetched in pass 2 (bis.gov.in blocked). |
| Standard pages | `routes/Explorer.tsx` | Explorer with tabs | Working, expert-oriented | e2e explorer test | No "at a glance" for beginners | fix (redesign) | Fixed: "At a glance" card (covers / who / status / source), tabs Overview · Important requirements · Full text & clauses · Related & compare · Ask about this. |
| Requirements | `ingest/requirements.py`, `routes/Requirements.tsx` | SHALL/SHOULD/MAY list, CSV | Working | e2e CSV test | — | keep; rename "Important requirements" | Kept; tab renamed "Important requirements". |
| Compare | `answer/compare.py`, `routes/Compare.tsx` | Aspect table + numeric limits | Working on demo pack only | e2e compare test used DEMO-101/102 | Only synthetic full texts existed | fix: works on official documents | Works on any indexed document (manuals included); example pair follows the loaded data. Official pair not run here. |
| Filters / library | `routes/Library.tsx` | Filters, typeahead | Working | e2e library test | — | keep | Kept. |
| Guided flow | — | "Beginner guided path" | **Dead (absent)** | Only a "Which product?" clarification chip set in answers | Not built | build | Built: `/guide` (goal → product or category from the data → real standards / normal pipeline); e2e. |
| Language selector | `components/Layout.tsx`, `i18n/*` | Drives UI + answers | Partial | UI strings switch (parity test); answer language follows UI; STT/TTS locale only for browser APIs | No server STT/TTS; lang not sent to voice | fix (single language context for STT/TTS too) | Fixed (pass 1): one language context for UI, answer, STT, TTS. Pass 2: "Ask in हिंदी/ಕನ್ನಡ" chip, examples per language, localised coverage and citations. |
| UI translation | `web/src/i18n/*.json` | en/hi/kn UI | Working | vitest key parity; Hindi/Kannada screenshots | — | keep | Kept; 98 new keys in all three languages (native review pending). |
| Content translation | `i18n/translate.py`, `protect.py` | Answers in hi/kn with identifiers protected | Working (with Groq gpt-oss-20b) | Live Hindi answer screenshot `demo-5-hindi.png`; protect tests | — | keep; add language-matrix e2e | Kept; optional labelled machine translation under quoted evidence (`/api/translate`). |
| **Microphone** | `components/SearchBar.tsx`, `lib/speech.ts` | Voice input in 3 languages | **Partial** | Code uses only `webkitSpeechRecognition`; no MediaRecorder, no level meter, no permission-error mapping; mic button hidden where unsupported (Firefox, many mobile browsers); never tested with audio | Browser-only design | **rewrite**: MediaRecorder → server STT, browser speech as fallback | Rewritten (pass 1): MediaRecorder → server STT, level meter, limits, cancel, error mapping, browser fallback; e2e with a fake microphone. Pass 2: spoken-number normalisation bug fixed. |
| **STT (server)** | `api/misc.py` `/api/voice/stt` | Optional server provider | **Fake / Dead** | Always returns 501 `voice_provider_not_configured` | Never implemented | **rewrite**: Groq Whisper (`whisper-large-v3-turbo`), keys server-side | Rewritten (pass 1): Groq Whisper, real audio fixtures en/hi/kn. `.env.example` corrected in pass 2. |
| **TTS** | `lib/speech.ts`, `Answer.tsx` | Read answer aloud | Partial | Browser `speechSynthesis` only; `getVoices()` read synchronously (often empty until `voiceschanged`); no sentence splitting; no stop on route/language change; no Kannada on typical desktops (this machine: English voices only) | Browser-only; timing bug | fix: voices event, chunking, state machine; server TTS where a provider exists (Groq Orpheus: English only); honest "not available" otherwise | Fixed (pass 1): voices event, chunking, one player, stop on route/language change, honest "not available"; e2e. |
| `/api/voice/tts` | `api/misc.py` | Server TTS | **Fake / Dead** | Always 501 | Never implemented | rewrite (Groq Orpheus English) | Rewritten (pass 1): Groq Orpheus, English only; hi/kn reported unsupported. |
| Exports | CSV, print checklist | Requirement export | Working | e2e download test | — | keep | Kept. |
| Retrieval details drawer | `RetrievalDrawer.tsx` | Expert view | Working | e2e opens; shows scores/drops | — | keep as "How this answer was found" | Kept (shows mode live/cached/evidence-only, scores, drops, timings). |
| Health/doctor | `api/misc.py`, `ops.py` | Diagnostics | Partial | Reports LLM + index; not STT/TTS/translation or language support | — | extend | Extended: voice, translation, per-language support (pass 1); reranker state with a plain fix (pass 2). |
| Answer layout | `components/Answer.tsx` | Readable answers | Partial | Summary + fact list + interpretation box; no "short answer / key points / what this means / next step" structure; evidence panel always open | Expert-first design | redesign | Redesigned: short answer · key points (exact wording collapsed) · what this means for you · standards · sources · next step; calmer refusal with guided-path and browse actions. |

## Fake / dead sweep (2026-09-28)

`grep -iE "mock|fake|dummy|stub|placeholder|lorem|TODO|FIXME|hardcoded|coming soon|not implemented|setTimeout|Math.random"` over `web/src` and `server/bisense`:
- No mocked answers, canned responses, random results or dead onClick handlers in the product code.
- `setTimeout` uses are UI timing only (toasts, debounce, scroll/focus after render) — not fake processing.
- **Dead**: `/api/voice/stt` and `/api/voice/tts` return 501 unconditionally → rewritten (see above).
- `FakeLLM` exists only for tests and is selected only by `LLM_PROVIDER=fake`; the answer cache is disabled in that mode.

## Data inventory (before this pass)

| Content | Where it came from | How it got in | Official? |
|---|---|---|---|
| 26 BIS web pages (certification, FMCS, Scheme-X, hallmarking, labs, consumers, FAQs) | www.bis.gov.in, allow-list in `data/public_sources.yaml` | `bisense fetch-public` → `data/public/` → ingest | Yes (official BIS website), URL + retrieval date recorded |
| Products under Compulsory Certification (Scheme-I, Scheme-II) | www.bis.gov.in | same | Yes; 924 product → IS rows, 735 metadata-only standards |
| Helmet QCO 2020, Plugs & sockets QCO 2019 | bis.gov.in copies of Gazette notifications | same | Yes (government notifications) |
| Grant of Licence guidelines, MSME cluster-lab guidelines | bis.gov.in PDFs | same | Yes (official BIS documents) |
| DEMO-101/102/201/301 | Written for this project | `data/demo/*.md` rendered to PDF | **No — synthetic** (loaded by default before this pass) |
| Glossary synonyms, HI/KN keyword map | Written for this project | `server/bisense/i18n/glossary.yaml` | Not content; used only to phrase searches |

## Pass 2 sweep (2026-09-28)

- Re-ran the facade grep over `web/src` and `server/bisense`: no new mocks, canned answers or dead handlers.
- **Found and fixed**: search crashed when the reranker model could not be downloaded; home "sample mode"
  banner never showed (`dataset_mode === "demo"` vs `"sample"`); `.env.example` documented a non-existent
  `STT_PROVIDER=browser` value and an unused `SARVAM_API_KEY`; Compare's example linked to sample documents in
  official mode; demo questions and `npm run warm` targeted sample documents; spoken "the limit is 10" became
  "IS 10"; eval reported refusal accuracy 0 whenever the reranker was off (it recomputed the gate instead of
  recording it).
