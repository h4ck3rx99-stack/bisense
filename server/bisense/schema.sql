-- BISense SQLite schema.
-- One file database (data/index/bisense.db), rebuilt by `bisense ingest`.
-- Every table here backs a visible feature; nothing speculative.

PRAGMA foreign_keys = ON;

-- A source file (PDF or HTML page) that was ingested.
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY,
    file_name       TEXT NOT NULL,
    sha256          TEXT NOT NULL UNIQUE,
    tier            TEXT NOT NULL,              -- A | B | C
    doc_type        TEXT NOT NULL,              -- standard | government_order | catalogue_page | guidance_page | synthetic_demo
    source_url      TEXT,
    obtained_on     TEXT,
    pages           INTEGER NOT NULL DEFAULT 1,
    language        TEXT NOT NULL DEFAULT 'en',
    synthetic       INTEGER NOT NULL DEFAULT 0,
    parser_version  TEXT NOT NULL,
    ocr_pages_json  TEXT NOT NULL DEFAULT '[]',
    warnings_json   TEXT NOT NULL DEFAULT '[]',
    ingested_at     TEXT NOT NULL
);

-- A browsable "source" in the library: an Indian Standard, a BIS guidance page, an official order,
-- or a catalogue-only standard entry (number + title known from an official list, no full text).
CREATE TABLE IF NOT EXISTS standards (
    id                        INTEGER PRIMARY KEY,
    slug                      TEXT NOT NULL UNIQUE,
    kind                      TEXT NOT NULL DEFAULT 'standard',  -- standard | guidance | order | catalogue
    number_canonical          TEXT,             -- "IS 302 (Part 1):2008", "DEMO-101:2026"; NULL for guidance pages
    base_number               TEXT,             -- "IS 302 (Part 1)" (no year) for matching
    part                      TEXT,
    section                   TEXT,
    year                      INTEGER,
    title                     TEXT NOT NULL,
    revision_label            TEXT,
    status                    TEXT NOT NULL DEFAULT 'unknown',
    status_verified_on        TEXT,
    category                  TEXT,
    industries_json           TEXT NOT NULL DEFAULT '[]',
    products_json             TEXT NOT NULL DEFAULT '[]',
    compulsory_certification  TEXT NOT NULL DEFAULT 'unknown',   -- yes | no | denotified | unknown
    compulsory_source         TEXT,
    compulsory_evidence_json  TEXT,             -- {slug, clause_number, page} of the official list row
    committee                 TEXT,
    ics                       TEXT,
    document_id               INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    catalogue_only            INTEGER NOT NULL DEFAULT 0,
    synthetic                 INTEGER NOT NULL DEFAULT 0,
    needs_review              INTEGER NOT NULL DEFAULT 0,
    source_url                TEXT,
    tier                      TEXT NOT NULL DEFAULT 'A'
);
CREATE INDEX IF NOT EXISTS idx_standards_base ON standards(base_number);

CREATE TABLE IF NOT EXISTS amendments (
    id            INTEGER PRIMARY KEY,
    standard_id   INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    label         TEXT NOT NULL,
    date          TEXT,
    text_excerpt  TEXT,
    page          INTEGER
);

CREATE TABLE IF NOT EXISTS clauses (
    id           INTEGER PRIMARY KEY,
    standard_id  INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    number       TEXT NOT NULL,           -- exactly as printed: "4.2.1", "A-2", "Table 3", "Q5"
    heading      TEXT NOT NULL DEFAULT '',
    path         TEXT NOT NULL DEFAULT '',
    level        INTEGER NOT NULL DEFAULT 1,
    parent_id    INTEGER REFERENCES clauses(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL DEFAULT 'other',
    page_start   INTEGER NOT NULL DEFAULT 1,
    page_end     INTEGER NOT NULL DEFAULT 1,
    text         TEXT NOT NULL DEFAULT '',
    ord          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clauses_standard ON clauses(standard_id, ord);

CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY,
    clause_id    INTEGER NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
    standard_id  INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    ord          INTEGER NOT NULL,
    text         TEXT NOT NULL,
    embed_text   TEXT NOT NULL,
    token_count  INTEGER NOT NULL,
    page_start   INTEGER NOT NULL,
    page_end     INTEGER NOT NULL,
    bbox_json    TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_standard ON chunks(standard_id);

-- Lexical index. Column order matters for bm25() weights (see retrieval/lexical.py).
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, heading, number, title,
    tokenize = 'porter unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS requirements (
    id             INTEGER PRIMARY KEY,
    standard_id    INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    clause_id      INTEGER NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
    chunk_id       INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
    text_verbatim  TEXT NOT NULL,
    modality       TEXT NOT NULL,       -- shall | shall_not | should | should_not | may | must
    topic          TEXT NOT NULL,       -- clause kind: requirement | test_method | marking | packing | ...
    page           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requirements_standard ON requirements(standard_id);

CREATE TABLE IF NOT EXISTS terms (
    id                   INTEGER PRIMARY KEY,
    standard_id          INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    clause_id            INTEGER NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
    term                 TEXT NOT NULL,
    definition_verbatim  TEXT NOT NULL,
    page                 INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS standard_refs (
    from_standard_id  INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    to_number         TEXT NOT NULL,
    to_standard_id    INTEGER REFERENCES standards(id) ON DELETE SET NULL,
    clause_id         INTEGER REFERENCES clauses(id) ON DELETE CASCADE
);

-- Product -> standard mappings, only from official Tier B documents (compulsory certification lists).
CREATE TABLE IF NOT EXISTS product_mappings (
    id                  INTEGER PRIMARY KEY,
    product_term        TEXT NOT NULL,
    standard_number     TEXT NOT NULL,
    source_document_id  INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    source_standard_id  INTEGER REFERENCES standards(id) ON DELETE CASCADE,
    clause_id           INTEGER REFERENCES clauses(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'compulsory',   -- compulsory | denotified
    note                TEXT
);

CREATE TABLE IF NOT EXISTS answer_cache (
    key             TEXT PRIMARY KEY,
    payload_json    TEXT NOT NULL,
    lang            TEXT NOT NULL,
    index_version   TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    source          TEXT NOT NULL,       -- live | warmed
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
