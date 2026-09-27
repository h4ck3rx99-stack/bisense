"""BISense command-line interface (typer).

    bisense ingest [PATH] [--rebuild] [--only NAME] [--ocr auto|off|force] [--dataset auto|real|demo]
    bisense fetch-public [--refresh]
    bisense inspect SLUG [--clause 4.2]
    bisense search "query" [--explain]
    bisense eval [--smoke]
    bisense warm
    bisense models
    bisense doctor

Every command prints human-readable output; nothing here is needed by the web app at runtime.
"""

from __future__ import annotations

import json
import sys

import typer

from bisense.config import get_settings

app = typer.Typer(add_completion=False, no_args_is_help=True, help="BISense: evidence-first assistant for Indian Standards")


def _utf8_stdout() -> None:
    # Windows consoles default to a legacy code page; Hindi/Kannada output needs UTF-8.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


@app.callback()
def _main() -> None:
    _utf8_stdout()


@app.command()
def ingest(
    rebuild: bool = typer.Option(False, help="Re-parse every file and rebuild the index"),
    only: str = typer.Option(None, help="Re-parse only this file (name or stem)"),
    ocr: str = typer.Option("auto", help="auto | off | force"),
    dataset: str = typer.Option(None, help="auto | real | demo (default: DATASET env)"),
) -> None:
    """Parse documents and (re)build the search index."""
    from bisense.ingest.pdf_parse import IngestError
    from bisense.ingest.pipeline import run_ingest

    settings = get_settings()
    try:
        report = run_ingest(settings, rebuild=rebuild, only=only, ocr_mode=ocr, dataset=dataset, log=typer.echo)
    except IngestError as exc:
        typer.secho(f"Ingest failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    if report.get("noop"):
        return
    _print_report(report)


def _print_report(report: dict) -> None:
    docs = report.get("documents", {})
    header = f"{'file':44} {'tier':4} {'pg':>3} {'garb':>4} {'cls':>4} {'chk':>4} {'tbl':>3} {'req':>4} {'term':>4} {'map':>4} {'warn':>4} rev"
    typer.echo(header)
    typer.echo("-" * len(header))
    totals = {k: 0 for k in ("pages", "clauses", "chunks", "tables", "requirements", "terms", "mappings")}
    for name, d in docs.items():
        typer.echo(
            f"{name[:44]:44} {d['tier']:4} {d['pages']:>3} {d['garbled_pages']:>4} {d['clauses']:>4} {d['chunks']:>4} "
            f"{d['tables']:>3} {d['requirements']:>4} {d['terms']:>4} {d['mappings']:>4} {len(d['warnings']):>4} {'yes' if d['needs_review'] else ''}"
        )
        for k in totals:
            totals[k] += d[k]
    typer.echo("-" * len(header))
    typer.echo(
        f"{len(docs)} documents, {totals['pages']} pages, {totals['clauses']} clauses, {totals['chunks']} chunks, "
        f"{totals['requirements']} requirements, {totals['terms']} terms, {totals['mappings']} official product mappings, "
        f"{report['catalogue_entries']} catalogue-only standards"
    )
    typer.echo(f"dataset mode: {report['dataset_mode']} (tiers {'+'.join(report['tiers'])})   index_version: {report['index_version']}")
    typer.echo(f"embedded {report['embedded_new']} new of {report['chunks_total']} chunks in {report['seconds']}s")
    for f in report.get("failures", []):
        typer.secho(f"  failed: {f['file']}: {f['error']}", fg=typer.colors.YELLOW)
    for f in report.get("drafted_manifest_entries", []):
        typer.secho(f"  drafted manifest entry (needs review): {f}", fg=typer.colors.YELLOW)
    typer.echo("Full report: data/index/ingest_report.json")


@app.command("fetch-public")
def fetch_public(refresh: bool = typer.Option(False, help="Download again even if present")) -> None:
    """Download Tier B official BIS pages listed in data/public_sources.yaml."""
    from bisense.ingest.fetch_public import fetch_all

    log = fetch_all(get_settings().data_dir, refresh=refresh, log=typer.echo)
    typer.echo(f"{len(log)} files recorded in data/public/fetch_log.yaml")


@app.command()
def inspect(slug: str, clause: str = typer.Option(None, help="Show one clause, e.g. 4.2")) -> None:
    """Print a standard's clause tree, chunks and requirements."""
    from bisense.db import connect

    conn = connect(get_settings().db_path, readonly=True)
    std = conn.execute("SELECT * FROM standards WHERE slug = ?", (slug,)).fetchone()
    if not std:
        typer.secho(f"No standard with slug '{slug}'. Try: bisense search \"{slug}\"", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo(f"{std['number_canonical'] or ''} {std['title']}  [{std['kind']}, tier {std['tier']}]")
    rows = conn.execute("SELECT * FROM clauses WHERE standard_id = ? ORDER BY ord", (std["id"],)).fetchall()
    for c in rows:
        if clause and c["number"] != clause and not c["number"].startswith(clause + "."):
            continue
        typer.echo(f"{'  ' * c['level']}{c['number']} {c['heading']}  <{c['kind']}, p.{c['page_start']}-{c['page_end']}>")
        if clause:
            typer.echo(c["text"])
            for ch in conn.execute("SELECT id, token_count, text FROM chunks WHERE clause_id = ?", (c["id"],)):
                typer.echo(f"    [chunk {ch['id']} ~{ch['token_count']} tok] {ch['text'][:160]!r}")
    reqs = conn.execute(
        "SELECT r.modality, c.number, r.text_verbatim FROM requirements r JOIN clauses c ON c.id = r.clause_id WHERE r.standard_id = ?", (std["id"],)
    ).fetchall()
    typer.echo(f"\n{len(reqs)} requirement statements")
    for r in reqs[:40]:
        if clause and not r["number"].startswith(clause):
            continue
        typer.echo(f"  {r['modality'].upper():10} {r['number']:8} {r['text_verbatim'][:120]}")


@app.command()
def search(
    query: str,
    explain: bool = typer.Option(False, "--explain", help="Show every retrieval stage and score"),
    lang: str = typer.Option("en"),
    no_rerank: bool = typer.Option(False, help="Disable the cross-encoder"),
) -> None:
    """Run retrieval only (no LLM) and print ranked evidence."""
    from bisense.retrieval.index import db_conn
    from bisense.retrieval.query import understand
    from bisense.retrieval.search import search as run_search

    conn = db_conn()
    plan = understand(conn, query, ui_lang=lang)
    res = run_search(conn, plan, rerank_enabled=False if no_rerank else None)
    typer.echo(f"intent={plan.intent} lang={plan.lang} english={plan.english_query!r} scope={[s.number or s.slug for s in plan.scope]}")
    if explain:
        typer.echo(f"lexical terms: {plan.lexical_terms}")
        typer.echo(f"timings (ms): {res.timings}   top rerank: {res.top_rerank}")
        typer.echo(f"{'#':>2} {'cite':4} {'lex':>5} {'vec':>6} {'fused':>7} {'rerank':>7}  source")
        for i, c in enumerate(res.candidates[:15], start=1):
            typer.echo(
                f"{i:>2} {c.citation_id or '':4} {str(c.lexical_rank or '-'):>5} {c.vector_score or 0:6.3f} {c.fused:7.4f} "
                f"{c.rerank_score if c.rerank_score is not None else float('nan'):7.2f}  {c.label()[:28]} · {c.clause_number} {c.clause_heading[:30]} (p.{c.page_start})"
            )
            typer.echo(f"      {c.text[:150]!r}")
    typer.echo("\nStandards:")
    for h in res.standards[:8]:
        typer.echo(f"  {h.number or '':22} {h.title[:60]:60} via={h.via} compulsory={h.compulsory} score={h.score:.2f}")
        if h.matched_row:
            typer.echo(f"      row: {h.matched_row[:140]}")


@app.command()
def doctor() -> None:
    """Check the environment and print how to fix each problem."""
    from bisense.ops import run_doctor

    checks = run_doctor()
    failed = False
    for c in checks:
        mark = "OK  " if c.ok else ("FAIL" if c.blocking else "WARN")
        color = typer.colors.GREEN if c.ok else (typer.colors.RED if c.blocking else typer.colors.YELLOW)
        typer.secho(f"[{mark}] {c.name}: {c.detail}", fg=color)
        if not c.ok and c.fix:
            typer.echo(f"       fix: {c.fix}")
        failed = failed or (not c.ok and c.blocking)
    if failed:
        typer.secho("Doctor found blocking problems (see fixes above).", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho("Environment looks good.", fg=typer.colors.GREEN)


@app.command()
def models() -> None:
    """Download the embedding and reranker models (once) so BISense works offline."""
    from bisense.ops import download_models

    download_models(log=typer.echo)


@app.command()
def warm() -> None:
    """Run the demo questions through the live pipeline and cache the validated results."""
    from bisense.ops import run_warm

    out = run_warm(log=typer.echo)
    typer.echo(json.dumps({k: v for k, v in out.items() if k != "items"}))


@app.command("eval")
def eval_cmd(
    no_llm: bool = typer.Option(False, "--no-llm", help="Retrieval and evidence gate only"),
    smoke: bool = typer.Option(False, "--smoke", help="Quick subset; does not write the report"),
    compare: bool = typer.Option(False, "--compare", help="Also compare reranker on/off (retrieval only)"),
    min_recall: float = typer.Option(0.0, help="Exit with an error if recall@5 is below this (used by `npm run check`)"),
) -> None:
    """Run the evaluation set and write docs/EVAL.md (real numbers only)."""
    from bisense.evaluation import main

    out = main(no_llm=no_llm, smoke=smoke, compare=compare, log=typer.echo)
    typer.echo(json.dumps(out["metrics"], indent=1))
    if out["calibration"]:
        typer.echo(f"recommended GATE_RERANK_MIN = {out['calibration']['threshold']}")
    for c in out["comparisons"]:
        typer.echo(json.dumps(c))
    if not smoke:
        typer.echo("Wrote the evaluation report (docs/EVAL.md or docs/eval/no_llm.json)")
    if (out["metrics"].get("recall_at_5") or 0) < min_recall:
        typer.secho(f"recall@5 below {min_recall}", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def openapi(out: str = typer.Option("openapi.json", help="Output path (relative to server/)")) -> None:
    """Write the OpenAPI schema (used by `npm run gen:types` to generate frontend types)."""
    from pathlib import Path

    from bisense import models
    from bisense.main import create_app

    schema = create_app().openapi()
    # SSE event payloads are not route responses; add them so the frontend gets generated types too.
    comps = schema.setdefault("components", {}).setdefault("schemas", {})
    for model in (models.StageEvent, models.EvidenceEvent, models.ErrorEvent, models.DoneEvent, models.AskTrace, models.QueryInfo, models.Answer):
        js = model.model_json_schema(ref_template="#/components/schemas/{model}", mode="serialization")
        for name, sub in js.pop("$defs", {}).items():
            comps.setdefault(name, sub)
        comps.setdefault(model.__name__, js)
    Path(out).write_text(json.dumps(schema, indent=1, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"wrote {out} ({len(schema.get('paths', {}))} paths)")


@app.command()
def report() -> None:
    """Print the last ingest report."""
    path = get_settings().index_dir / "ingest_report.json"
    if not path.exists():
        typer.echo("No ingest report yet. Run: npm run ingest")
        raise typer.Exit(1)
    _print_report(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    app()
