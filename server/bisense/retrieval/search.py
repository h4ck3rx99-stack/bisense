"""Hybrid retrieval orchestrator.

    plan (query.understand) -> lexical || vector -> RRF fuse + boosts -> rerank top 20
    -> diversify -> assemble context (C1..Cn) -> group by standard

All scores are kept on each candidate so the "Retrieval details" drawer and `bisense search --explain`
can show exactly why a passage was chosen.

Catalogue-only standards (number + title from an official BIS list, no full text) have no chunks of
their own. They are surfaced through the list rows that mention them: when a retrieved list chunk
contains a row matching the query, that row's standard is added to the grouped results with the row
as its evidence.
"""

from __future__ import annotations

import re
import sqlite3
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from bisense import stdnum
from bisense.config import get_settings
from bisense.listrow import parse_row
from bisense.retrieval.fuse import apply_boosts, rrf, topic_kinds
from bisense.retrieval.index import LoadedIndex, get_index
from bisense.retrieval.lexical import lexical_search
from bisense.retrieval.query import STOPWORDS, QueryPlan
from bisense.retrieval.vector import vector_search


@dataclass
class Candidate:
    chunk_id: int
    standard_id: int
    slug: str
    number: str | None
    title: str
    std_kind: str
    synthetic: bool
    tier: str
    clause_id: int
    clause_number: str
    clause_heading: str
    clause_kind: str
    clause_path: str
    page_start: int
    page_end: int
    text: str
    doc_type: str
    source_url: str | None
    has_pdf: bool
    text_scope: str = "full_text"
    document_title: str | None = None
    source_org: str | None = None
    source_type: str | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    vector_rank: int | None = None
    vector_score: float | None = None
    fused: float = 0.0
    boosts: dict = field(default_factory=dict)
    rerank_score: float | None = None
    citation_id: str | None = None

    def label(self) -> str:
        return self.number or self.title


@dataclass
class StandardHit:
    standard_id: int
    slug: str
    number: str | None
    title: str
    kind: str
    catalogue_only: bool
    synthetic: bool
    compulsory: str
    compulsory_source: str | None
    score: float
    via: str  # "full_text" | "official_list" | "guidance"
    evidence_chunk_ids: list[int] = field(default_factory=list)
    matched_row: str | None = None


@dataclass
class SearchResult:
    plan: QueryPlan
    candidates: list[Candidate]  # all reranked/fused candidates, best first
    context: list[Candidate]  # the passages given to the LLM, with citation ids
    standards: list[StandardHit]
    timings: dict[str, float]
    top_rerank: float | None
    reranked: bool


_CHUNK_SQL = """
SELECT ch.id AS chunk_id, ch.text, ch.page_start, ch.page_end, ch.standard_id,
       cl.id AS clause_id, cl.number AS clause_number, cl.heading AS clause_heading, cl.kind AS clause_kind, cl.path AS clause_path,
       s.slug, s.number_canonical, s.title, s.kind AS std_kind, s.synthetic, s.tier, s.source_url,
       s.text_scope, d.title AS document_title, d.source_org, d.source_type, d.doc_type, d.file_name
FROM chunks ch
JOIN clauses cl ON cl.id = ch.clause_id
JOIN standards s ON s.id = ch.standard_id
LEFT JOIN documents d ON d.id = s.document_id
WHERE ch.id IN ({ids})
"""


def load_candidates(conn: sqlite3.Connection, chunk_ids: list[int]) -> dict[int, Candidate]:
    if not chunk_ids:
        return {}
    rows = conn.execute(_CHUNK_SQL.format(ids=",".join("?" for _ in chunk_ids)), chunk_ids).fetchall()
    out = {}
    for r in rows:
        out[r["chunk_id"]] = Candidate(
            chunk_id=r["chunk_id"],
            standard_id=r["standard_id"],
            slug=r["slug"],
            number=r["number_canonical"],
            title=r["title"],
            std_kind=r["std_kind"],
            synthetic=bool(r["synthetic"]),
            tier=r["tier"],
            clause_id=r["clause_id"],
            clause_number=r["clause_number"],
            clause_heading=r["clause_heading"],
            clause_kind=r["clause_kind"],
            clause_path=r["clause_path"],
            page_start=r["page_start"],
            page_end=r["page_end"],
            text=r["text"],
            doc_type=r["doc_type"] or "",
            source_url=r["source_url"],
            has_pdf=bool(r["file_name"] and r["file_name"].lower().endswith(".pdf")),
            text_scope=r["text_scope"],
            document_title=r["document_title"],
            source_org=r["source_org"],
            source_type=r["source_type"],
        )
    return out


RERANK_TOP = 16
# Questions about legal/compulsory status should always consult the official product lists.
LEGAL_QUESTION_RE = re.compile(r"\b(compulsory|mandatory|isi|qco|quality control order|certification required|need (a )?(bis )?licen[cs]e)\b", re.I)
# "Do I need / is it compulsory / which standard" questions: official list rows rank above FAQs.
APPLIES_RE = re.compile(
    r"\b(do|does|is|are|will)\b[^?]*\b(need|needs|needed|require[sd]?|compulsory|mandatory|necessary)\b|"
    r"\b(which|what)\s+(indian\s+)?(standards?|is\s+(no|number)|bis\s+standards?)\b|\bstandards?\s+(for|of|applies?|applicable)\b|"
    r"\bneed(s|ed)?\s+(a\s+)?(bis|isi|crs|registration|licen[cs]e|certification)\b",
    re.I,
)
# Foreign Manufacturers Certification Scheme pages answer only questions about manufacturers abroad.
FOREIGN_RE = re.compile(r"\b(foreign|import|imports|importer|importing|imported|overseas|abroad|outside india|fmcs)\b", re.I)
_cache: OrderedDict[tuple, SearchResult] = OrderedDict()
_CACHE_MAX = 256


def search(conn: sqlite3.Connection, plan: QueryPlan, rerank_enabled: bool | None = None, top_k: int | None = None) -> SearchResult:
    settings = get_settings()
    index = get_index()
    rerank_enabled = settings.rerank_enabled if rerank_enabled is None else rerank_enabled
    top_k = top_k or settings.top_k_context
    key = (index.version, plan.english_query, tuple(plan.lexical_terms), plan.intent, tuple(plan.scope_ids), tuple(plan.explicit_ids), rerank_enabled, top_k)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    result = _search_uncached(conn, index, plan, rerank_enabled, top_k)
    _cache[key] = result
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return result


def _scope_filter(conn: sqlite3.Connection, plan: QueryPlan) -> tuple[list[int] | None, list[str]]:
    """Standard ids to hard-filter on, plus extra lexical phrases for catalogue-only scope items."""
    if not plan.scope:
        return None, []
    with_text = []
    extra_terms = []
    for s in plan.scope:
        has_chunks = conn.execute("SELECT 1 FROM chunks WHERE standard_id = ? LIMIT 1", (s.id,)).fetchone()
        if has_chunks:
            with_text.append(s.id)
        elif s.number:
            sn = stdnum.parse(s.number)
            if sn:
                extra_terms.append(f"{sn.prefix} {sn.number}")
    if with_text:
        return with_text, extra_terms
    return None, extra_terms


def _search_uncached(conn: sqlite3.Connection, index: LoadedIndex, plan: QueryPlan, rerank_enabled: bool, top_k: int) -> SearchResult:
    from bisense.retrieval.embed import embed_query

    timings: dict[str, float] = {}
    filter_ids, extra_terms = _scope_filter(conn, plan)
    terms = list(plan.lexical_terms) + extra_terms + [f"{n}" for n in _number_phrases(plan)]

    t = time.perf_counter()
    lex = lexical_search(conn, terms, limit=40, standard_ids=filter_ids)
    timings["lexical"] = _ms(t)

    t = time.perf_counter()
    qtext = plan.english_query
    if extra_terms:
        qtext = f"{qtext} {' '.join(extra_terms)}"
    vec = vector_search(index, embed_query(qtext), limit=40, standard_ids=filter_ids)
    timings["vector"] = _ms(t)

    t = time.perf_counter()
    fused = rrf([lex, vec])
    lex_rank = {cid: (i + 1, s) for i, (cid, s) in enumerate(lex)}
    vec_rank = {cid: (i + 1, s) for i, (cid, s) in enumerate(vec)}
    cands = load_candidates(conn, list(fused))
    meta = {cid: {"kind": c.clause_kind, "standard_id": c.standard_id} for cid, c in cands.items()}
    breakdown = apply_boosts(fused, meta, plan.intent, plan.explicit_ids, topic_kinds(plan.english_query))
    for cid, c in cands.items():
        c.lexical_rank, c.lexical_score = lex_rank.get(cid, (None, None))
        c.vector_rank, c.vector_score = vec_rank.get(cid, (None, None))
        c.boosts = breakdown[cid]
        c.fused = breakdown[cid]["total"]
        # Number mentioned in the query appears verbatim in the chunk (catalogue rows, orders).
        for phrase in extra_terms + _number_phrases(plan):
            if phrase and re.search(r"(?<![\w])" + re.escape(phrase) + r"(?![\d])", c.text):
                c.fused += 0.02
                c.boosts["mention_boost"] = 0.02
    ordered = sorted(cands.values(), key=lambda c: c.fused, reverse=True)
    timings["fuse"] = _ms(t)

    reranked = False
    top_rerank = None
    if rerank_enabled and ordered:
        t = time.perf_counter()
        from bisense.retrieval.rerank import RerankerUnavailable, rerank

        head = ordered[:RERANK_TOP]
        try:
            scores = rerank(plan.english_query, [_rerank_text(c) for c in head])
        except RerankerUnavailable:
            scores = None  # keep the fused (keyword + meaning) order; the gate then uses the stricter no-rerank rule
        if scores is not None:
            for c, s in zip(head, scores, strict=True):
                c.rerank_score = s
            head.sort(key=lambda c: (c.rerank_score or -99) + 20 * (c.boosts.get("number_boost", 0) + c.boosts.get("mention_boost", 0)), reverse=True)
            ordered = head + ordered[RERANK_TOP:]
            top_rerank = max(scores) if scores else None
            reranked = True
        timings["rerank"] = _ms(t)

    # FMCS (foreign manufacturers) pages come last unless the question is about importing/foreign makers:
    # "How do I apply for a BIS licence?" should answer from the domestic scheme.
    if not FOREIGN_RE.search(plan.english_query):
        ordered = [c for c in ordered if not _is_fmcs(c)] + [c for c in ordered if _is_fmcs(c)]

    # Official product lists: for discovery questions, put matching list rows first (they are the
    # only official evidence of which standard covers a product and whether certification is compulsory).
    applies = bool(APPLIES_RE.search(plan.english_query))
    if plan.intent in ("discover", "applicability") or applies or LEGAL_QUESTION_RE.search(plan.english_query):
        t = time.perf_counter()
        probe_all = product_probe(conn, plan)
        probe_ids = [cid for cid in probe_all if cid not in {c.chunk_id for c in ordered[:3]}]
        extra = load_candidates(conn, [cid for cid in probe_all if cid not in cands])
        cands.update(extra)
        for cid in probe_all:
            cands[cid].boosts["official_list"] = 1.0
        promoted = [cands[cid] for cid in probe_ids]
        # A matching official row is the answer to "do I need / which standard"; FAQs and pages follow it.
        if probe_all and (applies or plan.intent in ("discover", "applicability")) and ordered[:1] and ordered[0].chunk_id != probe_all[0]:
            ordered = [cands[cid] for cid in probe_all] + [c for c in ordered if c.chunk_id not in set(probe_all)]
        else:
            ordered = ordered[:1] + promoted + [c for c in ordered[1:] if c.chunk_id not in set(probe_ids)]
        timings["product_probe"] = _ms(t)

    # Clause lookup ("clause 4.3.1 of DEMO-101", "Table 2 of DEMO-301"): direct database lookup, placed first.
    if plan.clause_refs and plan.scope:
        direct = clause_lookup(conn, [s.id for s in plan.scope], plan.clause_refs)
        if direct:
            extra = load_candidates(conn, [cid for cid in direct if cid not in cands])
            cands.update(extra)
            for cid in direct:
                cands[cid].boosts["clause_lookup"] = 1.0
            ordered = [cands[cid] for cid in direct] + [c for c in ordered if c.chunk_id not in set(direct)]

    # Official list sections hold many unrelated products; keep only the header and the matching rows so
    # neither the LLM nor the reader can mistake a neighbouring row for an answer.
    for c in ordered[:30]:
        if c.clause_kind == "list":
            c.text = trim_list_rows(c.text, plan)

    t = time.perf_counter()
    context = _diversify(ordered, plan.intent, top_k, get_settings().context_token_budget)
    for i, c in enumerate(context, start=1):
        c.citation_id = f"C{i}"
    standards = group_standards(conn, ordered[:30], plan)
    timings["assemble"] = _ms(t)
    return SearchResult(plan=plan, candidates=ordered, context=context, standards=standards, timings=timings, top_rerank=top_rerank, reranked=reranked)


_GENERIC = STOPWORDS | {
    # question words: "Do ceiling fans NEED ISI mark?" must match "Electric Ceiling Type Fans" on fans alone
    *"need needs needed require requires required apply applies applicable which what does get use used standards".split(),
    *"certificate certified registration register approval approved rule rules law legal selling seller manufacturer".split(),
    *"manufacturing made making item items covers cover govern governs relevant".split(),
    "product",
    "products",
    "certification",
    "compulsory",
    "requirement",
    "requirements",
    "bis",
    "isi",
    "mark",
    "specification",
    "make",
    "manufacture",
    "sell",
    "business",
    "quality",
    "control",
    "order",
    "mandatory",
    "licence",
    "license",
    "standard",
    "scheme",
    "indian",
}


def _stem(w: str) -> str:
    w = w.lower()
    return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w


_GENERIC_STEMS = {_stem(g) for g in _GENERIC}


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[A-Za-z]{3,}", text)}


# Words that describe where or how a product is used, not what it is: "mobile charger" still matches
# "Power Adaptors for IT Equipments" when only such words are missing.
_CONTEXT_WORDS = {
    _stem(w)
    for w in "mobile phone cell home house household domestic kitchen electric electrical small new our buy online india indian good best cheap local office personal".split()
}


@dataclass
class ProductQuery:
    """The user's product words, plus alternative versions with everyday words replaced by the official
    product wording from the glossary ("LED bulbs" -> "self-ballasted LED lamps general lighting services")."""

    variants: list[set[str]]  # official-wording variants first, the user's own words last
    exp: set[str]  # extra words from the lexical synonym expansion
    phrases: list[str] = field(default_factory=list)  # official product wording, lower case

    @property
    def orig(self) -> set[str]:
        return self.variants[-1] if self.variants else set()

    def __iter__(self):  # `orig, exp = product_terms(plan)` keeps working
        return iter((self.orig, self.exp))


def product_terms(plan: QueryPlan) -> ProductQuery:
    """The user's content words (stemmed, generic words removed), official-wording variants and expansion words."""
    from bisense.i18n.glossary import product_phrases

    orig = {s for t in plan.content_terms for s in _stems(t)} - _GENERIC_STEMS
    exp = {s for t in plan.lexical_terms for s in _stems(t)} - _GENERIC_STEMS - orig
    variants: list[set[str]] = []
    phrases = [p.lower() for _, p in product_phrases(plan.english_query)]
    for key, phrase in product_phrases(plan.english_query):
        v = (orig - _stems(key)) | (_stems(phrase) - _GENERIC_STEMS)
        if v and v not in variants:
            variants.append(v)
    variants.append(orig)
    return ProductQuery(variants=variants, exp=exp, phrases=phrases)


def _match_one(words: set[str], orig: set[str], exp: set[str]) -> float:
    o = len(orig & words)
    if orig and o / len(orig) >= 0.7:
        return o / len(orig) + 0.5 * o / len(words)
    # Key words all present; only usage words ("mobile", "home") missing.
    missing = orig - words
    if o and missing and missing <= _CONTEXT_WORDS:
        return 0.6 + 0.1 * o / len(words)
    e = len(exp & words)
    if e >= 3:
        return 0.5 + 0.1 * e
    return 0.0


def product_match(product_text: str, orig: set[str] | ProductQuery, exp: set[str] | None = None) -> float:
    """How well a product name matches the query (0 = no match). Coverage of the user's words must be >= 70%
    (after replacing everyday words with the official product wording), or only usage words may be missing,
    or at least three glossary-expansion words must match (e.g. "TMT bars" -> "deformed steel bars")."""
    words = _stems(product_text)
    if not words:
        return 0.0
    if isinstance(orig, ProductQuery):
        score = max(_match_one(words, v, orig.exp) for v in orig.variants)
        # The official wording appears as written ("Safety of Toys ..." rather than "Safety of Electric Toys").
        text = " ".join(product_text.lower().split())
        if score and any(p in text for p in orig.phrases):
            score += 0.3
        return score
    return _match_one(words, orig, exp or set())


def product_probe(conn: sqlite3.Connection, plan: QueryPlan, limit: int = 3) -> list[int]:
    """Chunk ids of official list rows whose product name best matches the query's content words."""
    pq = product_terms(plan)
    if not any(pq.variants) and not pq.exp:
        return []
    scored: list[tuple[float, int, str, str]] = []
    for r in conn.execute("SELECT product_term, standard_number, clause_id FROM product_mappings WHERE clause_id IS NOT NULL"):
        score = product_match(r["product_term"], pq)
        if score > 0:
            scored.append((score, r["clause_id"], r["standard_number"], r["product_term"]))
    scored.sort(reverse=True)
    out: list[int] = []
    for _, clause_id, number, product in scored:
        sn = stdnum.parse(number)
        needle = (f"{sn.prefix} {sn.number}" if sn else number).replace(" ", "")
        rows = [
            ch for ch in conn.execute("SELECT id, text FROM chunks WHERE clause_id = ? ORDER BY ord", (clause_id,)) if needle in ch["text"].replace(" ", "")
        ]
        # One chunk per row: prefer the row for this product (several products can share a standard).
        best = next((ch for ch in rows if product[:40] in ch["text"]), rows[0] if rows else None)
        if best is not None and best["id"] not in out:
            out.append(best["id"])
        if len(out) >= limit:
            break
    return out


def trim_list_rows(text: str, plan: QueryPlan) -> str:
    """Keep the caption, the table header and the rows matching the query's product words or named
    standard numbers. Rows are copied verbatim; if nothing matches, the text is returned unchanged."""
    lines = text.splitlines()
    table = [i for i, ln in enumerate(lines) if ln.startswith("|")]
    if len(table) < 3:
        return text
    header_end = table[1] + 1  # header row + separator row
    pq = product_terms(plan)
    bases = {s.base for s in map(stdnum.parse, plan.explicit_numbers) if s}
    keep: list[str] = []
    for ln in lines[header_end:]:
        if not ln.startswith("|"):
            continue
        cells = [x.strip() for x in ln.strip().strip("|").split("|")]
        nums = stdnum.find_all(ln)
        if bases and any(n.base in bases for n in nums):
            keep.append(ln)
        elif not bases and product_match(" ".join(cells[2:-1]) if len(cells) > 3 else " ".join(cells[2:]), pq) > 0:
            keep.append(ln)
    if not keep:
        return text
    return "\n".join(lines[:header_end] + keep)


def clause_lookup(conn: sqlite3.Connection, standard_ids: list[int], refs: list[str]) -> list[int]:
    """Chunk ids of the named clauses (and their sub-clauses) within the scoped standards, in document order."""
    out: list[int] = []
    qs = ",".join("?" for _ in standard_ids)
    for ref in refs:
        ref = " ".join(ref.split())
        rows = conn.execute(
            f"SELECT ch.id FROM chunks ch JOIN clauses cl ON cl.id = ch.clause_id WHERE cl.standard_id IN ({qs}) "  # noqa: S608
            "AND (LOWER(cl.number) = LOWER(?) OR cl.number LIKE ?) ORDER BY cl.ord, ch.ord LIMIT 6",
            (*standard_ids, ref, f"{ref}.%"),
        ).fetchall()
        out += [r["id"] for r in rows if r["id"] not in out]
    return out


def _number_phrases(plan: QueryPlan) -> list[str]:
    out = []
    for n in plan.explicit_numbers:
        sn = stdnum.parse(n)
        if sn:
            out.append(f"{sn.prefix} {sn.number}" if sn.prefix != "DEMO" else f"DEMO-{sn.number}")
    return out


def _is_fmcs(c: Candidate) -> bool:
    return "foreign manufacturer" in f"{c.title} {c.document_title or ''}".lower()


def _rerank_text(c: Candidate) -> str:
    head = f"{c.number or ''} {c.title} — {c.clause_number} {c.clause_heading}".strip()
    return f"{head}\n{c.text}"[:700]  # longer inputs cost more CPU than they add in relevance signal


def _diversify(ordered: list[Candidate], intent: str, top_k: int, token_budget: int) -> list[Candidate]:
    per_standard_cap = 2 if intent in ("discover", "applicability") else 4
    per_clause_cap = 1 if intent in ("discover", "applicability") else 2
    row_cap = 3  # official list rows are one chunk each; neighbouring products in a category may all apply
    by_std: dict[int, int] = {}
    by_clause: dict[int, int] = {}
    out: list[Candidate] = []
    tokens = 0
    for c in ordered:
        cap = row_cap if c.clause_kind == "list" else per_clause_cap
        if (c.clause_kind != "list" and by_std.get(c.standard_id, 0) >= per_standard_cap) or by_clause.get(c.clause_id, 0) >= cap:
            continue
        cost = int(len(c.text.split()) * 1.3) + 20
        if out and tokens + cost > token_budget:
            continue
        out.append(c)
        tokens += cost
        by_std[c.standard_id] = by_std.get(c.standard_id, 0) + 1
        by_clause[c.clause_id] = by_clause.get(c.clause_id, 0) + 1
        if len(out) >= top_k:
            break
    return out


def group_standards(conn: sqlite3.Connection, ordered: list[Candidate], plan: QueryPlan) -> list[StandardHit]:
    """Group candidates by standard; surface catalogue standards from matching list rows."""
    hits: dict[int, StandardHit] = {}
    pq = product_terms(plan)

    def add(std_id: int, score: float, via: str, chunk_id: int, row: str | None = None) -> None:
        if std_id in hits:
            h = hits[std_id]
            h.score = max(h.score, score)
            if chunk_id not in h.evidence_chunk_ids:
                h.evidence_chunk_ids.append(chunk_id)
            if row and not h.matched_row:
                h.matched_row = row
            return
        r = conn.execute(
            "SELECT id, slug, number_canonical, title, kind, catalogue_only, synthetic, compulsory_certification, compulsory_source FROM standards WHERE id = ?",
            (std_id,),
        ).fetchone()
        if not r:
            return
        hits[std_id] = StandardHit(
            standard_id=r["id"],
            slug=r["slug"],
            number=r["number_canonical"],
            title=r["title"],
            kind=r["kind"],
            catalogue_only=bool(r["catalogue_only"]),
            synthetic=bool(r["synthetic"]),
            compulsory=r["compulsory_certification"],
            compulsory_source=r["compulsory_source"],
            score=score,
            via=via,
            evidence_chunk_ids=[chunk_id],
            matched_row=row,
        )

    # For product questions ("do I need / which standard"), the ranked evidence order already puts the
    # matching official row first; order the standards the same way (raw scores mix reranked and
    # unreranked passages and would let a neighbouring row win).
    by_position = (
        plan.intent in ("discover", "applicability") or bool(APPLIES_RE.search(plan.english_query)) or bool(LEGAL_QUESTION_RE.search(plan.english_query))
    )
    for rank, c in enumerate(ordered):
        score = (c.rerank_score if c.rerank_score is not None else c.fused * 100) - rank * 0.01
        if by_position:
            score = 30.0 - rank
        if c.clause_kind == "list":
            # rows of an official product list: surface the standards whose rows match the query
            explicit_bases = {s.base for s in map(stdnum.parse, plan.explicit_numbers) if s}
            row = parse_row(c.text)
            if row:
                nums = stdnum.find_all(row.numbers)
                if not nums:
                    continue
                if explicit_bases:
                    if not any(n.base in explicit_bases for n in nums):
                        continue
                    match = 1.0
                else:
                    match = product_match(f"{row.product} {row.title}", pq)
                    if match == 0:
                        continue
                r = conn.execute("SELECT id FROM standards WHERE base_number = ? ORDER BY (kind = 'catalogue') LIMIT 1", (nums[0].base,)).fetchone()
                if r:
                    add(r["id"], score + 0.1 * match if by_position else score - 0.5 + 2 * match, "official_list", c.chunk_id, c.text)
                continue
            for line in c.text.splitlines():
                if not line.startswith("|") or set(line) <= set("|-: "):
                    continue
                nums = stdnum.find_all(line)
                if not nums:
                    continue
                match = 1.0
                if explicit_bases:
                    if not any(n.base in explicit_bases for n in nums):
                        continue
                else:
                    cells = [x.strip() for x in line.strip().strip("|").split("|")]
                    # product (+ title) cells only; the notification cell mentions "Order" in every row
                    product_cells = " ".join(cells[2:-1]) if len(cells) > 3 else " ".join(cells[2:])
                    match = product_match(product_cells, pq)
                    if match == 0:
                        continue
                for sn in nums[:1]:
                    row = conn.execute("SELECT id FROM standards WHERE base_number = ? ORDER BY (kind = 'catalogue') LIMIT 1", (sn.base,)).fetchone()
                    if row:
                        add(row["id"], score - 0.5 + 2 * match, "official_list", c.chunk_id, " ".join(line.strip("|").split("|")).strip())
            continue
        via = "full_text" if c.std_kind == "standard" else "guidance"
        add(c.standard_id, score, via, c.chunk_id)

    for sid in plan.explicit_ids:
        if sid not in hits:
            r = conn.execute("SELECT kind FROM standards WHERE id = ?", (sid,)).fetchone()
            add(sid, 0.0, "catalogue" if r and r["kind"] == "catalogue" else "full_text", -1)
            if sid in hits:
                hits[sid].evidence_chunk_ids = [x for x in hits[sid].evidence_chunk_ids if x >= 0]
        if sid in hits:
            hits[sid].score += 100  # an explicitly named standard always ranks first
    return sorted(hits.values(), key=lambda h: h.score, reverse=True)


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)
