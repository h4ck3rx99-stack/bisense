"""The ingestion pipeline: files -> parsed documents -> SQLite index + embedding matrix.

Design (kept simple on purpose):
  1. Parse step, cached per file: each source file is parsed once per (sha256, parser version) and the
     result stored as JSON in data/processed/. Unchanged files are never re-parsed.
  2. Build step: the SQLite database is assembled from all parsed documents into a temporary file and
     swapped in atomically. This takes seconds, and it means the database can never be half-updated.
  3. Embed step: chunk vectors are cached by the hash of their embed_text, so only new or changed
     chunks are embedded.
  4. index_version = hash(file hashes + parser/chunker versions + embedding model + manifest). If it
     matches the existing index, ingest is a no-op.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from bisense import stdnum
from bisense.config import Settings
from bisense.db import connect, get_meta, init_schema, set_meta
from bisense.ingest import catalogue, html_parse, parse
from bisense.ingest.chunk import CHUNKER_VERSION, build_embed_text, chunk_clause
from bisense.ingest.demo_pack import build_demo_pack
from bisense.ingest.manifest import SourceFile, discover, draft_entry, save_manifest
from bisense.ingest.pdf_parse import IngestError
from bisense.ingest.requirements import extract_requirements
from bisense.ingest.terms import extract_amendments, extract_references, extract_terms
from bisense.ingest.types import ClauseDraft, ParsedDoc

Log = Callable[[str], None]

# Bump when build_database changes what it writes (part of index_version).
BUILDER_VERSION = "build-2"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def parser_version_for(path: Path, doc_type: str) -> str:
    if path.suffix.lower() == ".pdf":
        return parse.PARSER_VERSION
    if doc_type == "catalogue_page":
        return catalogue.PARSER_VERSION
    return html_parse.PARSER_VERSION


# ---------------------------------------------------------------------------------------------------
# Parse step (cached)
# ---------------------------------------------------------------------------------------------------


def _doc_to_json(doc: ParsedDoc) -> str:
    return json.dumps(dataclasses.asdict(doc), ensure_ascii=False)


def _doc_from_json(text: str) -> ParsedDoc:
    raw = json.loads(text)
    raw["clauses"] = [ClauseDraft(**c) for c in raw["clauses"]]
    return ParsedDoc(**raw)


def parse_file(sf: SourceFile, sha: str, processed_dir: Path, force: bool, ocr_mode: str) -> ParsedDoc:
    doc_type = sf.entry.get("doc_type", "standard")
    version = parser_version_for(sf.path, doc_type)
    cache = processed_dir / f"{sha[:16]}-{version}.json"
    if cache.exists() and not force:
        return _doc_from_json(cache.read_text(encoding="utf-8"))
    language = sf.entry.get("language", "en") or "en"
    if sf.path.suffix.lower() == ".pdf":
        doc = parse.parse_pdf_document(sf.path, language=language, ocr_mode=ocr_mode)
    elif doc_type == "catalogue_page":
        doc = catalogue.parse_catalogue_document(sf.path)
    else:
        doc = html_parse.parse_html_document(sf.path, language=language)
    processed_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(_doc_to_json(doc), encoding="utf-8")
    tmp.replace(cache)
    return doc


# ---------------------------------------------------------------------------------------------------
# Build step
# ---------------------------------------------------------------------------------------------------

KIND_BY_DOCTYPE = {
    "standard": "standard",
    "product_manual": "standard",
    "synthetic_demo": "standard",
    "guidance_pdf": "guidance",
    "guidance_page": "guidance",
    "catalogue_page": "guidance",
    "government_order": "order",
}


TEXT_SCOPE_BY_DOCTYPE = {
    "standard": "full_text",
    "product_manual": "product_manual",
    "synthetic_demo": "sample",
}


_ANNEX_RE = re.compile(r"^Annex(?:ure)?\s+([A-Z])$")
_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*$")


def qualify_annex_numbers(clauses: list[ClauseDraft]) -> None:
    """Number clauses inside an annex the way BIS prints them ("B-3.1"), so a numbered item in Annex B is never
    mistaken for clause 3.1 of the main text (product manuals restart numbering inside each annex)."""
    for c in clauses:
        if not _PLAIN_NUMBER_RE.match(c.number):
            continue
        j = c.parent
        while j is not None:
            m = _ANNEX_RE.match(clauses[j].number)
            if m:
                c.number = f"{m.group(1)}-{c.number}"
                break
            j = clauses[j].parent


def mark_manual_sections(clauses: list[ClauseDraft]) -> None:
    """Section numbers in a BIS product manual are the manual's own ("§2.1"), never clauses of the standard.
    The clause references *inside* the text (e.g. "Clause 6.7 of IS 4151") are left untouched."""
    for c in clauses:
        if _PLAIN_NUMBER_RE.match(c.number):
            c.number = f"§{c.number}"


def _clause_path(clauses: list[ClauseDraft], i: int) -> str:
    parts = []
    j: int | None = i
    while j is not None:
        c = clauses[j]
        label = f"{c.number} {c.heading}".strip() if c.number not in ("Front",) else c.heading
        parts.append(label)
        j = c.parent
    return " › ".join(reversed(parts))


def _standard_fields(sf: SourceFile, doc: ParsedDoc) -> dict:
    e = sf.entry
    doc_type = e.get("doc_type", "standard")
    kind = KIND_BY_DOCTYPE.get(doc_type, "standard")
    number = e.get("standard_number") or (doc.detected_number if kind == "standard" else None)
    sn = stdnum.parse(number) if number else None
    canonical = sn.canonical if sn else None
    if canonical:
        slug = stdnum.slugify_number(canonical)
    else:
        slug = stdnum.slugify_number(sf.path.stem)
    document_title = e.get("title") or doc.detected_title or sf.path.stem
    # A product manual is filed under its standard: the library row is titled with the standard's title.
    title = e.get("standard_title") or document_title
    status_verified = e.get("status_verified_on")
    if doc.last_updated and not status_verified:
        status_verified = doc.last_updated
    return {
        "slug": slug,
        "kind": kind,
        "number_canonical": canonical,
        "base_number": sn.base if sn else None,
        "part": sn.part if sn else None,
        "section": sn.section if sn else None,
        "year": sn.year if sn else doc.detected_year,
        "title": title,
        "revision_label": e.get("revision"),
        "status": e.get("status") or "unknown",
        "status_verified_on": status_verified,
        "category": e.get("category"),
        "industries_json": json.dumps(e.get("industries") or [], ensure_ascii=False),
        "products_json": json.dumps(e.get("products") or [], ensure_ascii=False),
        "compulsory_certification": e.get("compulsory_certification") or "unknown",
        "compulsory_source": e.get("compulsory_source"),
        "committee": e.get("committee"),
        "ics": e.get("ics"),
        "synthetic": 1 if e.get("synthetic") else 0,
        "needs_review": 1 if (e.get("needs_review") or sf.drafted) else 0,
        "source_url": e.get("source_url"),
        "tier": sf.tier,
        "text_scope": TEXT_SCOPE_BY_DOCTYPE.get(doc_type, "page"),
        "document_title": document_title,
        "source_org": e.get("source_org"),
        "source_type": e.get("source_type"),
        "verification_status": e.get("verification_status") or ("sample" if e.get("synthetic") else "unverified"),
        "access_note": e.get("access_note"),
    }


def _insert(conn: sqlite3.Connection, table: str, row: dict) -> int:
    cols = ", ".join(row)
    qs = ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", list(row.values()))  # noqa: S608 (column names are code constants)
    return int(cur.lastrowid or 0)


def build_database(db_path: Path, parsed: list[tuple[SourceFile, str, ParsedDoc]], dataset_mode: str, log: Log) -> tuple[list[tuple[int, str]], dict]:
    """Write all parsed documents into a fresh database. Returns (chunk_id, embed_text) pairs and stats."""
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    init_schema(conn)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    embed_rows: list[tuple[int, str]] = []
    per_doc: dict[str, dict] = {}
    standard_ids_by_base: dict[str, int] = {}
    pending_refs: list[tuple[int, str, int]] = []
    catalogue_rows: list[tuple[int, int, dict, dict[str, int]]] = []  # (doc_id, std_id, row, clause ids)

    for sf, sha, doc in parsed:
        e = sf.entry
        doc_id = _insert(
            conn,
            "documents",
            {
                "file_name": sf.path.name,
                "sha256": sha,
                "tier": sf.tier,
                "doc_type": e.get("doc_type", "standard"),
                "title": e.get("title"),
                "source_org": e.get("source_org"),
                "source_type": e.get("source_type"),
                "verification_status": e.get("verification_status") or "unverified",
                "access_note": e.get("access_note"),
                "source_url": e.get("source_url"),
                "obtained_on": e.get("obtained_on"),
                "pages": doc.pages,
                "language": doc.language,
                "synthetic": 1 if e.get("synthetic") else 0,
                "parser_version": parser_version_for(sf.path, e.get("doc_type", "standard")),
                "ocr_pages_json": json.dumps(doc.ocr_pages),
                "warnings_json": json.dumps(doc.warnings, ensure_ascii=False),
                "ingested_at": now,
            },
        )
        fields = _standard_fields(sf, doc)
        fields["document_id"] = doc_id
        if e.get("doc_type") == "product_manual":
            mark_manual_sections(doc.clauses)
        elif e.get("doc_type") == "standard":
            qualify_annex_numbers(doc.clauses)
        # Guard against slug collisions (two files for the same standard number).
        existing = conn.execute("SELECT id FROM standards WHERE slug = ?", (fields["slug"],)).fetchone()
        if existing:
            fields["slug"] = f"{fields['slug']}-{doc_id}"
        std_id = _insert(conn, "standards", fields)
        if fields["base_number"]:
            standard_ids_by_base[fields["base_number"]] = std_id

        # clauses
        clause_ids: list[int] = []
        for i, c in enumerate(doc.clauses):
            parent_id = clause_ids[c.parent] if c.parent is not None and c.parent < len(clause_ids) else None
            clause_ids.append(
                _insert(
                    conn,
                    "clauses",
                    {
                        "standard_id": std_id,
                        "number": c.number,
                        "heading": c.heading,
                        "path": _clause_path(doc.clauses, i),
                        "level": c.level,
                        "parent_id": parent_id,
                        "kind": c.kind,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "text": c.text if not c.table_rows else _table_text(c),
                        "ord": i,
                    },
                )
            )
        by_number = {c.number: clause_ids[i] for i, c in enumerate(doc.clauses)}

        # chunks + FTS
        n_chunks = 0
        chunk_of_clause: dict[int, list[tuple[int, str]]] = {}
        for i, c in enumerate(doc.clauses):
            path = _clause_path(doc.clauses, i)
            for k, ch in enumerate(chunk_clause(c.text, c.table_rows, heading=c.heading if c.table_rows else "", max_table_rows=8 if c.kind == "list" else 20)):
                cid = _insert(
                    conn,
                    "chunks",
                    {
                        "clause_id": clause_ids[i],
                        "standard_id": std_id,
                        "ord": k,
                        "text": ch.text,
                        "embed_text": build_embed_text(fields["number_canonical"], fields["title"], path, ch.text),
                        "token_count": ch.token_count,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "bbox_json": None,
                    },
                )
                conn.execute(
                    "INSERT INTO chunks_fts(rowid, text, heading, number, title) VALUES (?, ?, ?, ?, ?)",
                    (cid, ch.text, f"{c.number} {c.heading} {path}", fields["number_canonical"] or "", fields["title"]),
                )
                embed_rows.append((cid, build_embed_text(fields["number_canonical"], fields["title"], path, ch.text)))
                chunk_of_clause.setdefault(i, []).append((cid, ch.text))
                n_chunks += 1

        # requirements (deterministic)
        n_req = 0
        for i, c in enumerate(doc.clauses):
            if c.table_rows:
                continue
            for sentence, modality in extract_requirements(c.text, c.kind, fields["kind"]):
                chunk_id = None
                for cid, ctext in chunk_of_clause.get(i, []):
                    if sentence[:60] in " ".join(ctext.split()):
                        chunk_id = cid
                        break
                _insert(
                    conn,
                    "requirements",
                    {
                        "standard_id": std_id,
                        "clause_id": clause_ids[i],
                        "chunk_id": chunk_id,
                        "text_verbatim": sentence,
                        "modality": modality,
                        "topic": c.kind if c.kind != "table" else "requirement",
                        "page": c.page_start,
                    },
                )
                n_req += 1

        # terms
        terms = extract_terms(doc.clauses)
        for i, term, definition in terms:
            _insert(
                conn,
                "terms",
                {"standard_id": std_id, "clause_id": clause_ids[i], "term": term, "definition_verbatim": definition, "page": doc.clauses[i].page_start},
            )

        # references
        if fields["kind"] == "standard":
            for i, number in extract_references(doc.clauses, fields["number_canonical"]):
                pending_refs.append((std_id, number, clause_ids[i]))

        # amendments
        for a in extract_amendments(doc.clauses):
            _insert(conn, "amendments", {"standard_id": std_id, **a})

        for row in doc.catalogue_rows:
            catalogue_rows.append((doc_id, std_id, row, by_number))

        per_doc[sf.path.name] = {
            "slug": fields["slug"],
            "tier": sf.tier,
            "doc_type": e.get("doc_type"),
            "pages": doc.pages,
            "ocr_pages": len(doc.ocr_pages),
            "garbled_pages": len(doc.garbled_pages),
            "clauses": len(doc.clauses),
            "chunks": n_chunks,
            "tables": sum(1 for c in doc.clauses if c.kind == "table" or c.table_rows),
            "requirements": n_req,
            "terms": len(terms),
            "mappings": len(doc.catalogue_rows),
            "removed_lines": doc.removed_lines,
            "warnings": doc.warnings,
            "needs_review": bool(fields["needs_review"]),
        }

    # Official product -> standard mappings, and catalogue-only entries for standards without full text.
    n_catalogue = 0
    for doc_id, list_std_id, row, by_number in catalogue_rows:
        sn = stdnum.parse(row["standard_number"])
        if not sn:
            continue
        clause_id = by_number.get(row.get("clause_number", ""))
        list_slug = conn.execute("SELECT slug FROM standards WHERE id = ?", (list_std_id,)).fetchone()["slug"]
        evidence = json.dumps({"slug": list_slug, "clause_number": row.get("clause_number"), "page": 1})
        target_id = standard_ids_by_base.get(sn.base)
        status = "denotified" if row["status"] == "denotified" else "yes"
        source = (
            f"BIS list of products under compulsory certification — {row['order']}"
            if status == "yes"
            else "BIS list of products under compulsory certification: de-notified from compulsory BIS certification"
        )
        if target_id is None:
            slug = stdnum.slugify_number(sn.canonical)
            if conn.execute("SELECT 1 FROM standards WHERE slug = ?", (slug,)).fetchone():
                slug = stdnum.slugify_number(sn.base)
            if conn.execute("SELECT 1 FROM standards WHERE slug = ?", (slug,)).fetchone():
                slug = f"{slug}-{n_catalogue}"
            target_id = _insert(
                conn,
                "standards",
                {
                    "slug": slug,
                    "kind": "catalogue",
                    "number_canonical": sn.canonical,
                    "base_number": sn.base,
                    "part": sn.part,
                    "section": sn.section,
                    "year": sn.year,
                    "title": row["title"],
                    "status": "unknown",
                    "category": row.get("category"),
                    "industries_json": "[]",
                    "products_json": json.dumps([row["product"]], ensure_ascii=False),
                    "compulsory_certification": status,
                    "compulsory_source": source,
                    "compulsory_evidence_json": evidence,
                    "catalogue_only": 1,
                    "synthetic": 0,
                    "needs_review": 0,
                    "source_url": None,
                    "tier": "B",
                    "text_scope": "metadata_only",
                    "document_title": None,
                    "source_org": "Bureau of Indian Standards",
                    "source_type": "official_website",
                    "verification_status": "verified",
                    "access_note": "Number and title from the official BIS list of products under compulsory certification. The standard's text is not in BISense.",
                },
            )
            standard_ids_by_base[sn.base] = target_id
            n_catalogue += 1
        else:
            prods = json.loads(conn.execute("SELECT products_json FROM standards WHERE id = ?", (target_id,)).fetchone()[0] or "[]")
            if row["product"] not in prods:
                prods.append(row["product"])
            conn.execute(
                "UPDATE standards SET compulsory_certification = ?, compulsory_source = ?, compulsory_evidence_json = ?, products_json = ? WHERE id = ?",
                (status, source, evidence, json.dumps(prods, ensure_ascii=False), target_id),
            )
        _insert(
            conn,
            "product_mappings",
            {
                "product_term": row["product"],
                "standard_number": sn.canonical,
                "source_document_id": doc_id,
                "source_standard_id": list_std_id,
                "clause_id": clause_id,
                "status": "denotified" if row["status"] == "denotified" else "compulsory",
                "note": row["order"],
            },
        )

    # Resolve normative references to library standards.
    for from_id, number, clause_id in pending_refs:
        sn = stdnum.parse(number)
        to_id = standard_ids_by_base.get(sn.base) if sn else None
        conn.execute(
            "INSERT INTO standard_refs(from_standard_id, to_number, to_standard_id, clause_id) VALUES (?, ?, ?, ?)", (from_id, number, to_id, clause_id)
        )

    set_meta(conn, "dataset_mode", dataset_mode)
    conn.commit()
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('optimize')")
    conn.commit()
    conn.close()
    return embed_rows, {"documents": per_doc, "catalogue_entries": n_catalogue}


def _table_text(c: ClauseDraft) -> str:
    from bisense.ingest.tables import rows_to_markdown

    return rows_to_markdown(c.table_rows or [])


# ---------------------------------------------------------------------------------------------------
# Embed step (cached by text hash)
# ---------------------------------------------------------------------------------------------------


def embed_all(index_dir: Path, rows: list[tuple[int, str]], model_name: str, log: Log) -> tuple[int, int]:
    from bisense.retrieval.embed import embed_passages

    cache_path = index_dir / f"embed_cache-{stdnum.slugify_number(model_name)}.npz"
    cache: dict[str, np.ndarray] = {}
    if cache_path.exists():
        with np.load(cache_path) as z:
            keys = z["keys"]
            vecs = z["vecs"]
            cache = {str(k): vecs[i] for i, k in enumerate(keys)}
    hashes = [hashlib.sha1(t.encode("utf-8"), usedforsecurity=False).hexdigest() for _, t in rows]
    missing = [(h, t) for h, (_, t) in zip(hashes, rows, strict=True) if h not in cache]
    missing = list(dict(missing).items())
    if missing:
        log(f"embedding {len(missing)} new chunks with {model_name} ...")
        t0 = time.time()
        vecs = embed_passages([t for _, t in missing], model_name=model_name)
        for (h, _), v in zip(missing, vecs, strict=True):
            cache[h] = v
        log(f"  done in {time.time() - t0:.1f}s")
    dim = len(next(iter(cache.values()))) if cache else 0
    matrix = np.vstack([cache[h] for h in hashes]).astype(np.float32) if rows else np.zeros((0, dim), np.float32)
    ids = np.array([cid for cid, _ in rows], dtype=np.int64)

    _atomic_save_npy(index_dir / "embeddings.npy", matrix)
    _atomic_save_npy(index_dir / "chunk_ids.npy", ids)
    live = set(hashes)
    keys = np.array([k for k in cache if k in live])
    tmp = cache_path.with_suffix(".tmp.npz")
    np.savez(tmp, keys=keys, vecs=np.vstack([cache[k] for k in keys]) if len(keys) else np.zeros((0, dim)))
    os.replace(tmp, cache_path)
    return len(missing), len(rows)


def _atomic_save_npy(path: Path, arr: np.ndarray) -> None:
    tmp = path.with_suffix(".tmp.npy")
    np.save(tmp, arr)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------------------


def run_ingest(
    settings: Settings,
    rebuild: bool = False,
    only: str | None = None,
    ocr_mode: str = "auto",
    dataset: str | None = None,
    log: Log = print,
) -> dict:
    data_dir = settings.data_dir
    index_dir = settings.index_dir
    index_dir.mkdir(parents=True, exist_ok=True)
    dataset = dataset or settings.dataset

    discovery, entries = discover(data_dir, dataset)
    if "D" in discovery.tiers:
        build_demo_pack(data_dir / "demo")

    parsed: list[tuple[SourceFile, str, ParsedDoc]] = []
    failures: list[dict] = []
    drafted: list[str] = []
    for sf in discovery.files:
        if not sf.path.exists():
            failures.append({"file": sf.path.name, "error": "file listed in manifest but missing"})
            continue
        sha = sha256_file(sf.path)
        force = rebuild or (only is not None and only in (sf.path.stem, sf.path.name))
        try:
            doc = parse_file(sf, sha, data_dir / "processed", force=force, ocr_mode=ocr_mode)
        except IngestError as exc:
            failures.append({"file": sf.path.name, "error": str(exc)})
            log(f"  ! {exc}")
            continue
        if sf.drafted:
            sf.entry = draft_entry(sf.path, doc.detected_number, doc.detected_title)
            entries[sf.path.name] = sf.entry
            drafted.append(sf.path.name)
        parsed.append((sf, sha, doc))

    save_manifest(data_dir, entries)

    fingerprint = json.dumps(
        {
            "files": sorted(
                (sf.path.name, sha, sf.entry.get("title"), sf.entry.get("standard_number"), sf.entry.get("status"), sf.entry.get("compulsory_certification"))
                for sf, sha, _ in parsed
            ),
            "chunker": CHUNKER_VERSION,
            "builder": BUILDER_VERSION,
            "parsers": [parse.PARSER_VERSION, html_parse.PARSER_VERSION, catalogue.PARSER_VERSION],
            "model": settings.embedding_model,
            "dataset": discovery.dataset_mode,
        },
        sort_keys=True,
    )
    index_version = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]

    db_path = settings.db_path
    if db_path.exists() and not rebuild and not only and (index_dir / "embeddings.npy").exists():
        current = None
        try:
            existing = connect(db_path, readonly=True)
            try:
                current = get_meta(existing, "index_version")
            finally:
                existing.close()  # must close: Windows cannot replace an open file
        except sqlite3.Error:
            current = None
        if current == index_version:
            log(f"Index is up to date (index_version {index_version}); nothing to do.")
            report_path = index_dir / "ingest_report.json"
            return json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"index_version": index_version, "noop": True}

    t0 = time.time()
    tmp_db = index_dir / "bisense.build.db"
    embed_rows, stats = build_database(tmp_db, parsed, discovery.dataset_mode, log)
    new_vecs, total_vecs = embed_all(index_dir, embed_rows, settings.embedding_model, log)

    conn = connect(tmp_db)
    set_meta(conn, "index_version", index_version)
    set_meta(conn, "embedding_model", settings.embedding_model)
    set_meta(conn, "chunker_version", CHUNKER_VERSION)
    set_meta(conn, "built_at", datetime.now(UTC).isoformat(timespec="seconds"))
    conn.commit()
    conn.close()
    try:
        os.replace(tmp_db, db_path)
    except PermissionError as exc:
        raise IngestError(
            "Could not replace data/index/bisense.db because another process has it open. Stop the running BISense server and run ingest again."
        ) from exc

    report = {
        "index_version": index_version,
        "dataset_mode": discovery.dataset_mode,
        "tiers": discovery.tiers,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seconds": round(time.time() - t0, 1),
        "embedding_model": settings.embedding_model,
        "embedded_new": new_vecs,
        "chunks_total": total_vecs,
        "catalogue_entries": stats["catalogue_entries"],
        "documents": stats["documents"],
        "failures": failures,
        "drafted_manifest_entries": drafted,
    }
    (index_dir / "ingest_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (index_dir / "index_version.txt").write_text(index_version, encoding="utf-8")
    return report
