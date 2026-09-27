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
    reqs = conn.execute("SELECT r.modality, c.number, r.text_verbatim FROM requirements r JOIN clauses c ON c.id = r.clause_id WHERE r.standard_id = ?", (std["id"],)).fetchall()
    typer.echo(f"\n{len(reqs)} requirement statements")
    for r in reqs[:40]:
        if clause and not r["number"].startswith(clause):
            continue
        typer.echo(f"  {r['modality'].upper():10} {r['number']:8} {r['text_verbatim'][:120]}")


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
