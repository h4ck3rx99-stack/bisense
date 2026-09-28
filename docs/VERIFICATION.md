# Verification

What was checked, how, and what still needs a person. "Verified" means it was run and the result was
observed; compiling is not enough.

## Environment of the latest verification (2026-09-28, second repair pass)

- Linux container, Python 3.12 (uv), Node 22, Chromium 140 (Playwright, `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium`).
- **The network policy blocked `www.bis.gov.in`, `api.groq.com` and `huggingface.co`.** Consequences:
  - Official BIS data could not be fetched. The index was built in **sample mode** (`DATASET=sample`,
    4 Tier D documents, labelled everywhere). Tests that need official data skipped themselves with a reason.
  - No LLM, server STT or server TTS could be called. Answers ran in **extractive mode** (the honest
    no-LLM fallback); live-provider tests skipped.
  - The reranker model could not be downloaded. This exposed a real bug (search crashed); it now degrades
    to keyword + meaning ranking (see below). The embedding model came from fastembed's own public mirror.
- Earlier evidence from the first repair pass (same day, with network and a Groq key) is listed separately
  and marked **"previous pass"**. It was not re-run here.

## Quality gates (this pass)

| Command | Result |
|---|---|
| `npm run check` (ruff, ruff format, mypy, eslint, tsc, pytest, vitest, web build, eval smoke) | **Pass** — "All quality gates passed" |
| `npm run test` (backend) | 148 passed, 14 skipped (skips: official data not fetched, or no live LLM/STT/TTS key) |
| `npx vitest run` | 15 passed |
| `npm run e2e` (Playwright: desktop, 390×844 mobile, fake-microphone Chrome; axe on key pages; fails on any console error) | 23 passed, 2 skipped (real Whisper round trip — no key; official catalogue entry — no official data) |

## Feature by feature

| Feature | How verified (this pass) | Result | Still needs a person / real data |
|---|---|---|---|
| RAG is real: known-answer, ablation, refusal | `tests/test_rag_mechanism.py` (new, runs everywhere): a fact only in DEMO-301 is answered and cited to it; with DEMO-301 removed from the index the fact disappears, even when a fake model "knows" it; unrelated questions refused with zero LLM calls | Pass | The same proofs on official data: `tests/test_rag_proof.py` (IS 4151 product manual) — **previous pass: passed**; skipped here. Run `npm run fetch-public && npm run ingest && npm run test`. |
| Injection | `test_injected_instruction_in_sources_cannot_produce_unsupported_claims` (sample) | Pass | `test_injection_in_the_question_cannot_add_claims` on official data — previous pass |
| Validator (quotes, numbers, standard numbers, citations) | 15 adversarial tests in `test_validate.py` | Pass | — |
| LLM unavailable → evidence-only answer | `test_no_llm_gives_extractive_answer`, `test_llm_failure_falls_back_to_extractive`; screenshots `ask-desktop.png` show "AI summary unavailable right now; here is what the sources say" | Pass | — |
| Reranker unavailable (offline first run) | Found here: search raised an exception. Fixed: falls back to hybrid ranking; evidence gate switches to embedding similarity + (without LLM) content-word coverage. `test_health_reports_unavailable_reranker_with_a_fix`; eval without LLM and reranker: 11/12 unanswerable questions refused | Pass (degraded mode documented) | — |
| Ranking of topic words ("what must be **marked**") | `bisense search --explain`: marking clauses moved from ranks 5/9 to 1/2 | Pass | Re-run `npm run eval` on official data to confirm no regression (**not run here**) |
| Structured answer (short answer, key points, what this means, standards, sources, next step) | vitest asserts section order, AI label, human citation, no internal ids/scores; exact wording collapsed until asked; screenshots | Pass | Look at a live-LLM answer once (only extractive answers could be produced here) |
| Human citations + source badges | `humanSource()` builds "Bureau of Indian Standards · IS … · Clause … · Page …" from provenance fields, translated org/Clause/Page words; vitest + e2e | Pass | Click 10 citations on the official index and check source, clause and page (team) |
| Citation → evidence → exact clause | e2e `citation chip -> evidence card -> exact clause opens highlighted` | Pass | — |
| Guided path | e2e: goal → category (from `/api/library`) → real standards → open; goal + product description → normal ask pipeline | Pass | — |
| Home (30-second test) | e2e + screenshots desktop/mobile/hi/kn; examples chosen per language and data mode; coverage line localised | Pass | A first-time user test with someone outside the team |
| Standard page "At a glance" + tabs | e2e explorer test (tabs renamed), screenshot `explorer-mobile.png` | Pass | — |
| Compare | e2e `library filters and compare with numeric alignment` | Pass | Compare two official manuals (IS 4151 vs IS 2925) once data is fetched |
| Language selector drives UI, answer language, STT and TTS | e2e: switching changes `html lang` and strings; "Ask in हिंदी" re-asks in Hindi; answer `lang` = selected language (`test_retrieval`); recorder is cancelled on language change (e2e) | Pass | Translated answers need an LLM: **previous pass** verified Hindi and Kannada answers with identifiers preserved (`demo-5-hindi.png`) |
| Hindi / Kannada questions without an LLM | Real pipeline: "हेलमेट पर क्या चिह्न लगाना जरूरी है?", "ಹೆಲ್ಮೆಟ್ ಮೇಲೆ ಏನು ಗುರುತು ಇರಬೇಕು?", "पैकेज्ड पेयजल …" each retrieved the right clauses (glossary keyword fallback); screenshot `ask-desktop-hi.png` | Pass | Native-speaker review of strings (below) |
| Identifier protection in translation | `test_protect.py` incl. "IS 302 (Part 1):2008 clause 5.2.3 requires ≤ 0.5 mg/l" | Pass | — |
| UI string parity (en/hi/kn) | vitest key-parity test | Pass | — |
| Microphone states, errors, cleanup | e2e (fake-microphone Chrome): denied / no device / busy each explained with typing still working; cancel releases every track; STT 503 explained; language switch cancels recording | Pass | Real device check (below) |
| Server STT (Groq Whisper) | **previous pass**: live transcription tests in English, Hindi, Kannada with real audio (WAV/WebM/Ogg) and the fake-microphone → transcript → answer e2e. Here: skipped (api.groq.com blocked) | Not re-run | Run `npm run test` and `npm run e2e` with a Groq key |
| Spoken standard numbers | vitest: "I S fourteen five four three" → "IS 14543", "IS fourteen five forty three" → "IS 14543"; **fixed** "the limit is 10 mg" no longer becomes "IS 10" | Pass | — |
| Read-aloud (TTS) | e2e: chunks spoken in the answer language, stopped on navigation; "not available for this language on this device" shown honestly; text answer unaffected | Pass | Listening check (below). Server TTS (Groq Orpheus, English) — previous pass |
| Health / diagnostics | `/api/health`: index counts, dataset mode, LLM, voice and translation per language, **reranker state with a plain fix** (new) | Pass | — |
| `.env.example` matches the code | new `tests/test_config.py`; fixed `STT_PROVIDER=browser` / unused `SARVAM_API_KEY` | Pass | — |
| Security headers, rate limit, input validation, debug off by default | `test_api.py` | Pass | — |
| Accessibility | axe (WCAG 2.1 AA serious/critical = 0) on home, ask, explorer (also after the guided path), library, compare, about, mobile ask | Pass | Screen-reader pass with NVDA/TalkBack (team) |
| Docker image | Not built (no Docker in this environment) | Not verified | `docker build -t bisense .` |

## Manual checks for the team (about 10 minutes in total)

**Microphone and speech-to-text (2 minutes per device).** Desktop Chrome at `http://127.0.0.1:8000`, and one
phone over HTTPS (see "Serving over HTTPS" in the README; a LAN IP over plain http blocks the microphone).

1. Tap the mic. Allow access. The panel shows "Recording", a moving level meter and a timer.
2. Say "Which Indian Standard applies to helmets for two wheeler riders?", tap **Done**. The text appears in
   the box and can be edited before asking.
3. Switch to हिंदी, ask "हेलमेट के लिए कौन सा मानक है?"; switch to ಕನ್ನಡ, ask "ಹೆಲ್ಮೆಟ್‌ಗೆ ಯಾವ ಮಾನದಂಡ ಇದೆ?". Each transcript is in that script.
4. Block the microphone in the site settings, tap the mic: a plain message explains how to allow it, and typing still works.
5. Say "I S four one five one": the box shows "IS 4151".

**Read-aloud (1 minute).** On an answer, tap the speaker: it plays the short answer and key points, then
"Sources are shown on screen"; **Stop** stops it; asking a new question stops it. In Kannada on a laptop
without a Kannada voice, the control says it is not available — the answer text is unchanged.

**Citations (3 minutes, official data).** Ask the demo questions and open 10 citations: each must land on the
named document, clause/section and page, with the quoted sentence highlighted.

**Native-speaker review.** Hindi and Kannada strings in `web/src/i18n/hi.json` and `kn.json` (new this pass:
`answer.*`, `next.*`, `guide.*`, `glance.*`, `home.*`, `sourceType.*`, `cite.*`) and the keyword maps in
`server/bisense/i18n/glossary.yaml` were written without a native speaker.
