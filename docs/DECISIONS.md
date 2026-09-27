# Decisions log

One line per decision: what and why. Newest at the bottom.

- 2026-09-27 — Stack: FastAPI + SQLite/FTS5 + NumPy vectors + fastembed (ONNX) + React/Vite/TS. Why: empty repo; the brief's default stack is the lowest-risk path for beginners and runs offline.
- 2026-09-27 — Python 3.12 via uv (`server/.python-version`). Why: wheels for onnxruntime/pymupdf exist on Windows; 3.13+ not in the brief's range.
- 2026-09-27 — Official problem statement fetched from sih.gov.in (see PROBLEM_STATEMENT.md). It adds BIS *services* (schemes, hallmarking, labs, consumers). Why it matters: the library indexes official BIS service pages (Tier B) in addition to standards.
- 2026-09-27 — Tier B source list is a hand-picked allowlist of bis.gov.in pages and PDFs (`data/public_sources.yaml`); robots.txt checked (only /wp-admin/ disallowed); 3 s delay; fetcher never follows discovered links. Why: legitimate, polite, reproducible.
- 2026-09-27 — No Tier A PDFs are available to the build (BIS full texts need a portal login). Dataset `auto` therefore loads Tier B + Tier C. Deviation from the brief ("A/B else C"): Tier B alone cannot exercise clause-level features, so C is added whenever A is absent. Tier C is labelled synthetic everywhere.
- 2026-09-27 — Tier C demo pack: 4 synthetic documents (DEMO-101/102 water pair for compare, DEMO-201 helmets, DEMO-301 steel bars) rendered to PDF with fpdf2, including a simulated per-page licence watermark so stripping is exercised on the real PDF path.
- 2026-09-27 — The official "Products under Compulsory Certification" lists become (a) cited list clauses, (b) 924 product→IS mappings and (c) 735 catalogue-only standard entries ("Metadata only. Full text not indexed."). Why: the only official evidence for "is certification compulsory for my product".
- 2026-09-27 — Bilingual Gazette orders: English half indexed, Devanagari/legacy-font lines dropped with a warning. Why: the plugs/sockets QCO uses a legacy Hindi font that extracts as garbage.
- 2026-09-27 — Ingest = cached per-file parse (data/processed/<sha>-<parser>.json) + full DB rebuild into a temp file + atomic replace + embedding cache by text hash. Why: simplest correct idempotency; rebuild takes ~2 s.
- 2026-09-27 — FTS5 table stores its own copy of text (not contentless). Why: simple deletes/rebuilds, corpus is small.
- 2026-09-27 — ONNX threads per model = 2 at query time (ONNX_THREADS). Measured: with default threads, embedder+reranker sessions contend (rerank 16 docs: 3–5 s); with 2 threads each: query embed ~15 ms, rerank ~1.2–1.8 s for 16×700-char passages.
- 2026-09-27 — /api/search never reranks (instant results, ~10–50 ms warm). /api/ask reranks when RERANK_ENABLED (gate + ordering). Final choice recorded after eval (docs/EVAL.md).
- 2026-09-27 — Reranker input truncated to 700 chars; catalogue list chunks split into 8-row groups. Why: CPU cost of cross-encoder/embedding scales with length.
- 2026-09-27 — Product probe: official list rows are matched deterministically by stemmed word coverage (≥60% of the user's content words, or ≥3 glossary-expansion words) and promoted for discover/applicability/legal questions. Why: dense+BM25 alone let a demo document crowd out the official row.
- 2026-09-27 — Local LLM for development: Ollama `llama3.2` (3B) at ~40 tok/s on the laptop GPU; `qwen3:8b` measured 2.3 tok/s (VRAM spill) so not used. Ollama started with OLLAMA_CONTEXT_LENGTH=8192 because the default 4096 truncates 3k-token prompts. Cloud free tiers documented in .env.example.
- 2026-09-27 — Summary sentences without citation markers are kept only if they contain no numbers/standard numbers; the UI labels the summary as AI-written. Why: small models often omit markers; facts live in the validated points.
