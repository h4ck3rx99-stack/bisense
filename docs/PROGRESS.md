# Progress

## Current step
Repair, verify and redesign pass — complete for everything that can be verified without network access.
Remaining items need the team (official data fetch, keys, real devices, native speakers).

## Done
- First build (2026-09-27): ingestion, hybrid retrieval, grounded answering + validator, translation, compare,
  explorer, requirements, en/hi/kn UI, eval harness, tests, docs.
- Repair pass 1 (2026-09-28, with network): reality audit; official-only default data with tiers A–D and
  provenance; 12 official BIS product manuals; coverage line; RAG proof tests on official data; server STT
  (Groq Whisper) and TTS (Groq Orpheus, English); MediaRecorder microphone with level meter, limits, cancel
  and error mapping; robust read-aloud; one language context; LLM alternate model on rate limit.
- Repair pass 2 (2026-09-28, network blocked):
  - Reliability: reranker failure degrades instead of crashing search; fallback evidence gate; health reports
    reranker state with a fix; `.env.example` matches the code (tested); `npm run check` recall gate applies
    only with official data; `PW_CHROMIUM_PATH` for Playwright.
  - RAG: always-on proof tests on the sample pack (known-answer, ablation incl. a model that "knows",
    refusal); topic-aware ranking ("marked" → marking clauses); evidence-only answers drop weak passages
    and list only the standards they show; eval records the real gate decision.
  - UX: structured answer (short answer, key points with collapsed exact wording, "What this means for you",
    standard cards, human sources, next steps incl. "Ask in हिंदी/ಕನ್ನಡ"); human citations and source badges;
    guided path; new home (one message, one input, five doors, What is BIS?, localized coverage); standard
    page "At a glance" + beginner tab names; compare example that exists in the loaded data.
  - Language: examples per language; optional labelled machine translation under quoted evidence
    (`/api/translate`); spoken-number normalisation no longer corrupts "is 10".
  - Data: glossary maps everyday product words to official wording; demo questions and J1 eval question use
    official data; DATA.md rewritten for tiers A–D.
  - Docs: VERIFICATION (new), README, DATA, DEMO_SCRIPT, DECISIONS, REALITY_AUDIT, JUDGE_REVIEW; screenshots.

- Repair pass 3 (2026-09-28, network available): mic without a key (local Whisper, en/hi); resilient
  official-data download; official index built and evaluated (recall@5 1.00); RAG proofs on official data
  pass; e2e 26/26; readable no-key answers; category names; launcher upgrades existing installs.

## In progress
- (none)

## Next (team — cannot be done from a network-blocked environment)
1. Done in pass 3 (official data, proofs, eval without LLM). Remaining: `npm run eval` WITH a Groq key to
   refresh docs/EVAL.md answer metrics.
2. Add a Groq key to `.env`, run `npm run test` and `npm run e2e` again (live STT/TTS/LLM tests), then
   `npm run warm`.
3. Manual checks in docs/VERIFICATION.md (microphone on desktop Chrome and a phone over HTTPS, read-aloud,
   10 citations).
4. Native-speaker review of Hindi/Kannada strings and glossary keywords.
5. Rehearse docs/DEMO_SCRIPT.md twice.

## Known issues
- Not verified in this pass: anything needing bis.gov.in, Groq or HuggingFace (see VERIFICATION.md).
- Without both the reranker model and an LLM, refusal accuracy is lower (11/12 in the eval).
- Answer p50 ≈ 5.6 s with Groq (pass 1 measurement), above the 5 s budget.
- Docker image not built in either pass.

## Cut features
- Session-scoped PDF upload — not built (ALLOW_UPLOADS has no effect).
- Hindi/Kannada server voice — no free provider verified; device voices are used and the UI is honest.
- Reference-graph visualisation, dark mode — not built.
