# Data: sources, tiers, manifest and re-indexing

## Tiers

| Tier | Folder | What | How it gets there | Commit to git? |
|---|---|---|---|---|
| A | `data/raw/`, `data/public/` | **Official BIS documents**: Indian Standards the team downloads with its own legitimate BIS account (`data/raw/`), and official BIS PDFs such as the 12 product manuals and licensing guidelines (`data/public/`) | Standards: the team, through official BIS channels, following their terms; never from mirrors, never bypassing logins or CAPTCHAs. Manuals/guidelines: `npm run fetch-public` | **No** |
| B | `data/public/` | **Official BIS website**: certification schemes, FAQs, hallmarking, laboratories, consumer pages, the lists of products under compulsory certification | `npm run fetch-public` downloads the allow-list in `data/public_sources.yaml` (robots.txt respected, 3 s between requests, stops on errors, records URL + date) | **No** |
| C | `data/public/` | **Government notifications**: Quality Control Orders / Gazette notifications (copies hosted on bis.gov.in) | same | **No** |
| D | `data/demo/` | **Sample data, not official**: 4 documents written for this project (`DEMO-101`, `DEMO-102`, `DEMO-201`, `DEMO-301`), rendered to PDF | Written for this project; values are illustrative | Yes |

`DATASET` in `.env`:

- `official` (default) — Tiers A + B + C only. Sample data is never loaded or cited.
- `sample` — adds Tier D. Every sample item is labelled "Sample data, not official" on every screen,
  answer, citation, badge and export, and the home page shows a "Sample mode" banner.

Older values still work: `auto`/`real` mean `official`, `demo` means `sample`. The active mode is shown in
the UI and in `/api/health`.

## Provenance fields

Every document and standard carries: `source_org`, `source_type` (`official_document` |
`official_website` | `government_notification` | `sample`), `source_url`, `obtained_on` (retrieval date),
`verification_status`, `access_note`, `text_scope` (`full_text` | `product_manual` | `page` |
`metadata_only` | `sample`), plus standard number, title, revision/amendment data and page/clause per
passage. Citations are built from these fields only, e.g.
"Bureau of Indian Standards · Product Manual for IS 4151:2015 · Section 2 · Page 2".
`tests/test_rag_proof.py` fails if any indexed official record lacks them or if any Tier D record appears
in the default mode.

## Coverage honesty

The home page and `/api/library` state coverage in plain words ("BISense currently covers N standards
(full text available for M …)"). Standards known only from the official lists answer "what is it / what
does it cover" from their official title; for clause-level questions the answer says the full text is not
available in BISense and links the official source. A product manual is shown as a manual — its section
numbers are never presented as clauses of the standard.

## Re-verification

1. `npm run fetch-public` — re-downloads every allow-listed official file and records the new date in
   `data/public/fetch_log.yaml`.
2. `npm run ingest` — rebuilds the index; titles and numbers come from the official lists and manuals.
3. `npm run test` — `tests/test_rag_proof.py` (provenance, known-answer, ablation, refusal, injection on the
   official data) now runs instead of skipping.
4. `npm run eval` — retrieval and answer metrics on 63 questions (see docs/EVAL.md).

## Adding real standards (Tier A)

1. Obtain the PDF through an official BIS channel and save it in `data/raw/` (e.g. `IS-14543-2016.pdf`).
2. Add an entry to `data/sources.yaml` (or let ingestion draft one):

```yaml
- file: IS-14543-2016.pdf
  tier: A
  standard_number: IS 14543:2016
  title: Packaged Drinking Water (Other Than Packaged Natural Mineral Water) — Specification
  doc_type: standard
  source_url: <the official page you downloaded it from>
  obtained_on: 2026-09-30
  status: current            # current | withdrawn | superseded | unknown
  status_verified_on: 2026-09-30
  category: Food and drinking water
  industries: [Beverages]
  products: [packaged drinking water, bottled water]
  compulsory_certification: unknown   # only "yes" with an official order/list reference below
  compulsory_source: null
  language: en
  synthetic: false
  needs_review: false
```

3. Run `npm run ingest`. Files without an entry get a drafted one with `needs_review: true`, which the UI
   shows as "Metadata not yet verified" until someone checks it on the BIS website.
4. When a Tier A standard has the same number as a catalogue entry from the official lists, the two are
   merged: the full text replaces "Metadata only", and the compulsory-certification evidence is kept.

Per-page licence lines on BIS-distributed PDFs (name, email, date, IP) are detected and removed during
ingestion and never shown (tested in `server/tests/test_clean.py`).

## Manifest fields

`file, tier, standard_number, title, doc_type (standard | product_manual | government_order | catalogue_page | guidance_page | synthetic_demo), source_url, obtained_on, status, status_verified_on, category, industries[], products[], compulsory_certification (yes | no | unknown), compulsory_source, language, synthetic, needs_review`.
Entries for `data/public` and `data/demo` are regenerated by ingestion; edit only Tier A entries by hand. The manifest always
wins over values guessed from the document.

## Re-indexing

- `npm run ingest` — incremental: unchanged files are not re-parsed, unchanged chunks are not re-embedded.
  If nothing changed it prints "Index is up to date". A running server picks up the new index automatically.
- `npm run ingest -- --rebuild` — re-parse everything.
- `npm run ingest -- --only DEMO-101` — re-parse one file.
- `npm run inspect -- demo-101-2026 --clause 4.3` — print a document's clause tree, chunks and requirements.
- `npm run search:explain -- "query"` — print every retrieval stage with scores.
- The report is in `data/index/ingest_report.json` (pages, garbled/OCR pages, clauses, chunks, tables,
  requirements, terms, mappings, warnings per document).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "page N: no text layer (scanned image)" | Scanned PDF | Install Tesseract (eng + hin) and run `ocrmypdf in.pdf out.pdf`, put the OCR'd PDF in `data/raw/`. |
| "text looks garbled (legacy font)" / "non-English or garbled lines dropped" | Old Hindi fonts (e.g. Kruti Dev) that are not Unicode | The English part is indexed; for Hindi text get a Unicode PDF. Garbage is never indexed. |
| "not a PDF file" / "encrypted" | Wrong or protected file | Re-download; export an unprotected copy. |
| "Could not replace data/index/bisense.db" | Another process holds the file open (Windows) | Stop the server/eval, run ingest again. |
| A clause tree looks wrong | Unusual numbering or layout | `npm run inspect -- <slug>`; heading rules live in `server/bisense/ingest/structure.py`. |
