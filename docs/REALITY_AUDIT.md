# Reality audit

Started 2026-09-28 for the "repair, verify and redesign" pass. One row per feature. Status: Working / Partial /
Broken / Fake / Dead. Decision: keep / fix / rewrite / remove. "Evidence" is what was run or read, not a claim.
Rows are updated as fixes land (see the "After" column).

| Feature | Files | What it claims | Status (before) | Evidence | Root cause | Decision | After |
|---|---|---|---|---|---|---|---|
| Search / retrieval | `server/bisense/retrieval/*` | Hybrid BM25 + embeddings + RRF + reranker | Working | Eval 62 q: recall@5 1.00, exact hit 1.00 (docs/EVAL.md); `bisense search --explain` | — | keep | — |
| AI answers (RAG) | `answer/ask.py`, `generate.py` | Answers only from retrieved passages | Working | LLM receives only `<sources>` blocks; validator; eval refusal 1.00 | — | keep; add known-answer / ablation proof tests | — |
| Citations | `answer/validate.py`, `components/Evidence.tsx` | Citations tied to retrieved chunks | Working but expert-styled | Citation ids validated against context; UI shows `[n]` chips + raw clause numbers | Designed for experts; no human-format label, scores visible in cards | fix (human citation format; scores only in expert panel) | — |
| **Default data** | `ingest/manifest.py`, `data/demo` | Official data | **Partial / misleading by default** | `DATASET=auto` loads the synthetic DEMO pack whenever no Tier A PDFs exist; the only clause-level "standards" are synthetic | Earlier design treated synthetic data as a default fallback | **rewrite**: official-only by default; synthetic = opt-in sample mode | — |
| Official data | `data/public_sources.yaml` | BIS pages, lists, QCOs | Working | 32 official files with URL + date in `data/public/fetch_log.yaml` | — | keep; add official product manuals + department listings | — |
| Standard pages | `routes/Explorer.tsx` | Explorer with tabs | Working, expert-oriented | e2e explorer test | No "at a glance" for beginners | fix (redesign) | — |
| Requirements | `ingest/requirements.py`, `routes/Requirements.tsx` | SHALL/SHOULD/MAY list, CSV | Working | e2e CSV test | — | keep; rename "Important requirements" | — |
| Compare | `answer/compare.py`, `routes/Compare.tsx` | Aspect table + numeric limits | Working on demo pack only | e2e compare test used DEMO-101/102 | Only synthetic full texts existed | fix: works on official documents | — |
| Filters / library | `routes/Library.tsx` | Filters, typeahead | Working | e2e library test | — | keep | — |
| Guided flow | — | "Beginner guided path" | **Dead (absent)** | Only a "Which product?" clarification chip set in answers | Not built | build | — |
| Language selector | `components/Layout.tsx`, `i18n/*` | Drives UI + answers | Partial | UI strings switch (parity test); answer language follows UI; STT/TTS locale only for browser APIs | No server STT/TTS; lang not sent to voice | fix (single language context for STT/TTS too) | — |
| UI translation | `web/src/i18n/*.json` | en/hi/kn UI | Working | vitest key parity; Hindi/Kannada screenshots | — | keep | — |
| Content translation | `i18n/translate.py`, `protect.py` | Answers in hi/kn with identifiers protected | Working (with Groq gpt-oss-20b) | Live Hindi answer screenshot `demo-5-hindi.png`; protect tests | — | keep; add language-matrix e2e | — |
| **Microphone** | `components/SearchBar.tsx`, `lib/speech.ts` | Voice input in 3 languages | **Partial** | Code uses only `webkitSpeechRecognition`; no MediaRecorder, no level meter, no permission-error mapping; mic button hidden where unsupported (Firefox, many mobile browsers); never tested with audio | Browser-only design | **rewrite**: MediaRecorder → server STT, browser speech as fallback | — |
| **STT (server)** | `api/misc.py` `/api/voice/stt` | Optional server provider | **Fake / Dead** | Always returns 501 `voice_provider_not_configured` | Never implemented | **rewrite**: Groq Whisper (`whisper-large-v3-turbo`), keys server-side | — |
| **TTS** | `lib/speech.ts`, `Answer.tsx` | Read answer aloud | Partial | Browser `speechSynthesis` only; `getVoices()` read synchronously (often empty until `voiceschanged`); no sentence splitting; no stop on route/language change; no Kannada on typical desktops (this machine: English voices only) | Browser-only; timing bug | fix: voices event, chunking, state machine; server TTS where a provider exists (Groq Orpheus: English only); honest "not available" otherwise | — |
| `/api/voice/tts` | `api/misc.py` | Server TTS | **Fake / Dead** | Always 501 | Never implemented | rewrite (Groq Orpheus English) | — |
| Exports | CSV, print checklist | Requirement export | Working | e2e download test | — | keep | — |
| Retrieval details drawer | `RetrievalDrawer.tsx` | Expert view | Working | e2e opens; shows scores/drops | — | keep as "How this answer was found" | — |
| Health/doctor | `api/misc.py`, `ops.py` | Diagnostics | Partial | Reports LLM + index; not STT/TTS/translation or language support | — | extend | — |
| Answer layout | `components/Answer.tsx` | Readable answers | Partial | Summary + fact list + interpretation box; no "short answer / key points / what this means / next step" structure; evidence panel always open | Expert-first design | redesign | — |

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
