# Progress

## Current step
11 — Complete. Final judge review done (docs/JUDGE_REVIEW.md).

## Done
- Inspection (empty repo); official SIH26107 text; plan, decisions, architecture, data docs.
- Ingestion: PDF/HTML/catalogue parsers, cleaning (watermarks, garbled Hindi), clause trees, tables, requirements, terms, refs, amendments, 924 official product mappings, embeddings; idempotent; fresh-clone verified.
- Data: 32 official bis.gov.in files (Tier B) + 4-document synthetic demo pack (Tier C).
- Retrieval: hybrid FTS5 + embeddings + RRF + reranker, product probe, clause lookup, list-row trimming, context follow-ups.
- Answering: gate, prompts, validator (15 adversarial tests), retry, extractive fallback, LLM-declined fallback, cache, warm, translation with placeholders (separate translation model), compare, plain-language requirements.
- API + SSE; security headers; rate limit; debug trace.
- Frontend: home, ask (evidence-first, thread, drawer), library, explorer (5 tabs), checklist, compare, about, 404; en/hi/kn; voice; responsive; axe-clean.
- Tests: 125 pytest, 9 vitest, 13 Playwright (desktop + mobile, axe, no console errors). `npm run check` green.
- Evaluation: 62 questions; final live run recall@5 1.00, exact 1.00, refusal 1.00, false refusals 0.06.
- Docs: README, ARCHITECTURE, DATA, EVAL, DEMO_SCRIPT, TEAM_GUIDE, DECISIONS, JUDGE_REVIEW; screenshots.

## In progress
- (none)

## Next (team)
- Add real IS PDFs to data/raw + manifest; native review of hi/kn strings; spot-check eval questions; rehearse the demo; `npm run warm` on demo day.

## Known issues
- Answer p50 ≈ 5.6 s (budget 5 s). Docker build not executed here. Voice not tested with a real microphone.

## Cut features
- Session-scoped PDF upload (COULD) — not built; ALLOW_UPLOADS has no effect.
- Server STT/TTS providers (COULD) — endpoints return 501; browser speech only.
- Reference-graph visualisation, dark mode (COULD) — not built.
- Multilingual embedding model comparison — not run; the English pivot met the recall target (Hindi/Kannada questions retrieved at recall@5 1.0).
