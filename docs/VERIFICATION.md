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

## Pass 4 (2026-09-28, network and a Groq key)

- `pytest`: **175 passed, 0 skipped** (live Groq Whisper in English/Hindi/Kannada, local Whisper, RAG proofs on
  official data). `vitest`: 15 passed. Playwright: **26 passed, 0 skipped**, including the real round trip
  fake microphone → Groq Whisper → transcript in the box → answer.
- `npm run eval` with `openai/gpt-oss-120b` (alternate `openai/gpt-oss-20b`), 63 questions, on the e2e index
  (official data + labelled sample pack): recall@5 **0.98**, MRR@10 0.86, exact-number hit@1 **1.00**,
  refusal accuracy **0.917** (11/12), false refusals **0.02**, drop rate 0.017, fact hit **1.00**,
  answer p50 **1.5 s** / p95 4.2 s (pass 1: 5.6 s). 2 of 63 answers fell back to verbatim passages after a
  provider rate limit (noted per question in `docs/eval/latest.json`). This run used prompt `answer_v2`;
  the two fixes below (`answer_v2.1` + validator rule) were checked on the failing cases and by tests, and
  a full re-run is **pending** (Groq's daily allowance was used up by this run).
- Live browser checks (official index): English, Hindi and Kannada questions answered and cited to the
  official list rows and product manuals; guided path on official categories.
- Found and fixed:
  - The top bar showed "12 full-text" standards; they are BIS product manuals (0 full-text standards). Now
    "12 product manuals"; the "not found" page counts were corrected the same way.
  - Sample mode: a live summary credited a sample document's "eight helmets" to the official IS 4151 manual
    (which says 9). The validator now drops any statement citing both sample and official sources
    (`test_sample_and_official_sources_are_never_merged_into_one_statement`).
  - Eval u08 ("impact test speed for bicycle helmets") was answered from the two-wheeler helmet document.
    Prompt rule: sources about a different product or without the asked value → "not in the sources".
    Re-checked live: now refused with the gap named.
  - Groq free tier has a **daily** cap (200k tokens and 1k requests per model). After it, every question
    was a slow failed call. Now the client honours the provider's wait, stops calling the exhausted model,
    and the answer says "today's free AI allowance is used up, back in about N min"
    (`test_daily_provider_limit_is_reported_and_not_retried`). Eval waits out the limit instead of scoring
    fallbacks.
  - e2e depended on the working index being in sample mode (8 failures on a default official-only index).
    It now builds and uses `data/index-e2e` (`INDEX_PATH`), leaving `data/index` untouched.
- `npm run warm` (official index): 8 demo answers cached live; the Kannada hallmark question, the three standard
  summaries and the compare fell back to verbatim passages because the daily allowance ran out mid-run; the
  "fine in Karnataka" question was correctly refused. Re-run the day before the demo.
- Server read-aloud (Groq Orpheus) returns `model_terms_required`: the account admin must accept the model's
  terms once in the Groq console. Browser voices are used meanwhile; the UI reports it.

## Pass 3 (2026-09-28, network available, no Groq key)

- Official data downloaded (44 files, one dropped connection recovered by retry); index: 42 official documents,
  12 product manuals, 924 official product rows, 729 metadata-only standards; real embedding and reranker models.
- `pytest`: 166 passed, 7 skipped (Groq-only tests). Includes `test_rag_proof.py` on the official data
  (known-answer, ablation, refusal, injection, provenance) — run for the first time since pass 1.
- `vitest`: 15 passed. Playwright: **26 passed, 0 skipped** with `E2E_STT_PROVIDER=local` (real microphone
  flow via local Whisper, official catalogue entry, guided path on official categories).
- `bisense eval --no-llm` on 63 questions (official + sample index): recall@5 **1.00**, MRR@10 0.89,
  exact-number hit@1 1.00, refusal accuracy 0.83, false refusals 0.02 (same as before the ranking changes).
  Journey J1 "plastic food containers": expected manual at rank 2; the answer lists IS 17569 (compulsory),
  IS 10910, IS 6312, IS 15410 and the official list row for insulated food containers.
- Found and fixed while verifying: two allow-listed BIS pages are now empty landing pages (removed); one
  official category name was a whole paragraph of order history (cleaned); list rows printed raw table
  markup in no-key answers (now readable rows, and not labelled as exact wording); no-key "which standard"
  answers showed marking/annex boilerplate (now one about-passage per standard, list rows first);
  an `.env` from the old example (`STT_PROVIDER=browser`) kept the new mic off (old values now mean `auto`);
  the launcher would not install the new speech parts for existing users (setup-version check).

## Quality gates (pass 2)

| Command | Result |
|---|---|
| `npm run check` (ruff, ruff format, mypy, eslint, tsc, pytest, vitest, web build, eval smoke) | **Pass** — "All quality gates passed" |
| `npm run test` (backend) | 149 passed, 14 skipped (skips: official data not fetched, or no live LLM/STT/TTS key) |
| `npx vitest run` | 15 passed |
| `npm run e2e` (Playwright: desktop, 390×844 mobile, fake-microphone Chrome; axe on key pages; fails on any console error) | 24 passed, 2 skipped (real Whisper round trip — no key; official catalogue entry — no official data) |

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
| Quoted evidence stays original; optional machine translation | e2e (Hindi UI): passage marked `lang="en"`, "अनुवाद दिखाएँ" → with no working model the UI says translation is unavailable and keeps the original; `test_translate_protects_identifiers_and_degrades_honestly` (IS 302, 0.5 mg/l survive; size limits) | Pass | A real Hindi/Kannada translation of a passage needs an LLM key |
| Identifier protection in translation | `test_protect.py` incl. "IS 302 (Part 1):2008 clause 5.2.3 requires ≤ 0.5 mg/l" | Pass | — |
| UI string parity (en/hi/kn) | vitest key-parity test | Pass | — |
| Microphone states, errors, cleanup | e2e (fake-microphone Chrome): denied / no device / busy each explained with typing still working; cancel releases every track; STT 503 explained; language switch cancels recording | Pass | Real device check (below) |
| Microphone with **no key** (local Whisper) — pass 3 | Root cause of "mic doesn't ask for permission": without a key the mic never called `getUserMedia`; it used the browser recognizer (missing in Firefox, broken in Brave) or showed "unavailable". Now local Whisper runs on the server. `tests/test_voice_local.py` (real audio): English WebM, Hindi in Devanagari, Kannada refused (garbled in our test), silence → no speech; e2e `E2E_STT_PROVIDER=local`: fake mic → permission → level meter → local Whisper → "which Indian standard applies to helmets for two wheeler riders" in the box → answer | Pass | Permission prompt on a real browser (below) |
| Official data download — pass 3 | `npm run fetch-public` against bis.gov.in: the old code stopped at file 3 after a dropped connection and still wrote the log; the new code retried and completed 44/44 files ("All official files are present."). `tests/test_fetch_public.py`: retry, skip, resume, domain allow-list | Pass | — |
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
