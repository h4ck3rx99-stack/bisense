# Progress

## Current step
6 — Frontend core (Home, /ask, explorer, library).

## Done
- Inspection (empty repo), official SIH26107 text saved, Tier B fetch (32 official BIS files), Tier C demo pack.
- Ingestion: PDF/HTML/catalogue parsers, cleaning (watermarks, garbled Hindi), clause trees, tables, requirements, terms, refs, amendments, product mappings, embeddings, idempotent rebuild.
- Retrieval: query understanding, FTS5 + vectors + RRF + reranker + product probe, context assembly, CLI `search --explain`.
- Answering: prompts, LLM client (primary/fallback, JSON), validator (15 adversarial tests), extractive fallback, cache, translation with placeholders, SSE pipeline.
- API: health, library, standards list/suggest/detail/clause/requirements/csv/summary/page image, search, ask (SSE), compare, voice stubs, debug trace.

## In progress
- Frontend.

## Next
- Eval set + calibration, CLI eval/warm/doctor, tests, root scripts, docs, e2e.

## Known issues
- Reranker costs ~1.5 s per ask on this CPU.

## Cut features
- (none yet)
