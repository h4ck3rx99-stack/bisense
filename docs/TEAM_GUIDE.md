# Team guide

Plain-language map of BISense so each of the six of us can explain our part to the judges.

## Who owns what (for judge Q&A)

| Person | Area | Files | Be ready to explain |
|---|---|---|---|
| 1 | Ingestion | `server/bisense/ingest/` | How a PDF becomes clauses with page numbers; watermark stripping; tables; why ingest is idempotent; Tier A/B/C |
| 2 | Retrieval | `server/bisense/retrieval/` | BM25 + embeddings + RRF + reranker; exact standard numbers; the official-list product probe; `npm run search:explain` |
| 3 | Answering & validation | `server/bisense/answer/` | Evidence gate; prompt channels; the validator's checks; extractive fallback; why answers are not streamed token by token |
| 4 | Frontend | `web/src/` | Evidence-first `/ask`; citation → clause; explorer; compare; accessibility; mobile |
| 5 | Multilingual & voice | `server/bisense/i18n/`, `web/src/i18n/`, `web/src/lib/speech.ts` | English pivot; placeholder protection ⟦0⟧; Hindi/Kannada UI; browser voice input and read-aloud |
| 6 | Demo & evaluation | `server/eval/`, `server/bisense/evaluation.py`, `docs/EVAL.md`, `docs/DEMO_SCRIPT.md` | Real metrics and what they mean; gate calibration; `npm run warm`; offline backup plan |

## Code map (one line per module)

**Server** (`server/bisense/`)
- `config.py` settings from `.env` · `db.py` + `schema.sql` SQLite tables · `models.py` API contract (Pydantic) · `stdnum.py` standard-number parsing ("IS302(Part1):2008" → "IS 302 (Part 1):2008") · `main.py` FastAPI app · `cli.py` the `bisense` command · `ops.py` doctor/warm/models · `evaluation.py` the eval.
- `ingest/`: `fetch_public.py` polite downloader · `pdf_parse.py` PyMuPDF lines and tables · `clean.py` watermarks, headers, garbled Hindi · `structure.py` clause tree · `html_parse.py` BIS web pages · `catalogue.py` official product lists · `demo_pack.py` renders the synthetic PDFs · `chunk.py` · `requirements.py` SHALL/SHOULD/MAY · `terms.py` definitions, references, amendments · `manifest.py` provenance · `pipeline.py` puts it together.
- `retrieval/`: `query.py` language, intent, identifiers, context · `lexical.py` FTS5 · `embed.py` + `vector.py` embeddings · `fuse.py` RRF · `rerank.py` cross-encoder · `search.py` orchestration · `index.py` loads the index.
- `answer/`: `generate.py` prompts · `validate.py` the checks · `ask.py` the SSE pipeline · `extractive.py` · `confidence.py` · `cache.py` · `compare.py` · `plain.py` · `present.py` · `prompts/` versioned prompt files.
- `i18n/`: `languages.py` registry · `glossary.yaml` synonyms and offline HI/KN keywords · `protect.py` placeholders · `translate.py`.
- `api/`: `ask.py` (search, ask) · `standards.py` (library, explorer, requirements, CSV, page images, summary) · `misc.py` (health, compare, voice, eval, debug) · `common.py` (errors, rate limit).

**Web** (`web/src/`)
- `routes/`: `Home`, `Ask`, `Library`, `Explorer`, `Requirements`, `Checklist`, `Compare`, `About`, `NotFound`.
- `components/`: `Answer` (answer block, strength, scope chip, refusal), `Evidence` (citation chips, evidence cards), `SearchBar` (mic), `RetrievalDrawer`, `PagePreview`, `Layout` (top bar, footer), `StandardPicker`, `Markdown`, `Toast`, `ui`.
- `api/`: `types.gen.ts` (generated — never edit), `client.ts`, `sse.ts`. `i18n/`: `en.json`, `hi.json`, `kn.json`, `languages.ts`. `styles/index.css`: all design tokens.

## How to…

- **Add a real standard**: put the PDF in `data/raw/`, add its entry to `data/sources.yaml` (see docs/DATA.md), `npm run ingest`, then `npm run inspect -- <slug>` to check the clause tree.
- **Add an official BIS page**: add it to `data/public_sources.yaml` (bis.gov.in only), `npm run fetch-public`, `npm run ingest`.
- **Add a language (Tamil, Telugu, Marathi…)**: one entry in `server/bisense/i18n/languages.py` and `web/src/i18n/languages.ts`, a new `web/src/i18n/<code>.json` (copy `en.json`; the parity test fails until every key exists), optional `keywords_<code>` in `glossary.yaml`.
- **Change a UI text**: edit the three JSON files in `web/src/i18n/` (never hard-code English in components).
- **Change the LLM**: edit `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` in `.env`; `npm run doctor` checks it.
- **Tune the refusal gate**: run `npm run eval`, read the calibration section of docs/EVAL.md, set `GATE_RERANK_MIN` in `.env`.
- **Add a synonym** ("TMT" → "deformed steel bars"): `server/bisense/i18n/glossary.yaml` → `synonyms`.
- **Debug a bad answer**: open "Retrieval details" in the UI (candidates, scores, removed statements), or `npm run search:explain -- "question"`.
- **Change the API**: edit `server/bisense/models.py` and the route, then `npm run gen:types`.

## Glossary

- **RAG** (retrieval-augmented generation): first find relevant passages, then let the LLM write an answer from only those passages.
- **BM25**: the classic keyword-ranking formula; great for exact terms and standard numbers. SQLite FTS5 provides it.
- **Embeddings**: numbers that represent meaning; similar sentences get similar vectors. We compare them with cosine similarity.
- **RRF** (reciprocal rank fusion): combine two ranked lists by adding 1/(60 + rank) from each list; no score calibration needed.
- **Reranker (cross-encoder)**: a small model that reads the question and a passage together and scores relevance; slower but more accurate.
- **Evidence gate**: if the best passage's reranker score is too low, BISense refuses without calling the LLM.
- **Validator**: code (not AI) that checks every citation, quote, number and identifier in the AI's draft against the sources.
- **SSE** (server-sent events): one HTTP response that streams several events, so the browser shows evidence before the answer.
- **Placeholder protection**: before translation, numbers/standard numbers become ⟦0⟧, ⟦1⟧ … and are put back exactly afterwards.

## Before the demo

1. `npm run doctor`, then `npm run warm` (needs internet and the LLM key) — do this the morning of the demo.
2. Rehearse [DEMO_SCRIPT.md](DEMO_SCRIPT.md) twice, once with Wi-Fi off.
3. Spot-check the auto-drafted eval questions (`server/eval/questions.yaml`, `origin: auto_drafted`) and change `origin` to `team_verified` when checked.

## Hindi and Kannada strings needing native-speaker review

All strings in `web/src/i18n/hi.json` and `web/src/i18n/kn.json` were drafted by the build and need review, in particular:
- legal wording: `legal.*`, `compulsory.*`, `req.header`, `footer.disclaimer`, `standard.catalogueOnlyBody`;
- honesty messages: `insufficient.*`, `answer.extractive*`, `answer.interpretationTitle`;
- technical terms: `clauseKind.*` (e.g. "अंकन" for marking, "ಮಾದರಿ ಸಂಗ್ರಹ" for sampling), `modality.*Help`;
- the Hindi/Kannada keyword lists in `server/bisense/i18n/glossary.yaml` (used for offline search).
Also review the two example questions on the home page (`web/src/routes/Home.tsx`).
