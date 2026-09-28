"""Operational commands behind `bisense doctor`, `bisense warm` and `bisense models`.

doctor  - checks the environment and prints a human-readable fix for every problem.
warm    - runs docs/demo_questions.yaml, demo summaries and compare pairs through the LIVE pipeline and
          stores the validated results in the answer cache (source = warmed) for offline/flaky demos.
models  - downloads the embedding and reranker models so the app works offline afterwards.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass

import yaml

from bisense.config import REPO_ROOT, get_settings


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    blocking: bool = True


def run_doctor() -> list[Check]:
    s = get_settings()
    checks: list[Check] = []
    v = sys.version_info
    checks.append(
        Check(
            "Python 3.11/3.12",
            v[:2] in ((3, 11), (3, 12)),
            f"{v.major}.{v.minor}.{v.micro}",
            "Install Python 3.12 and run: npm run setup (uv picks the right version)",
        )
    )
    node = shutil.which("node")
    if node:
        out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        major = int(out.lstrip("v").split(".")[0]) if out.startswith("v") else 0
        checks.append(Check("Node.js 20+", major >= 20, out, "Install Node.js 20 LTS or newer from nodejs.org"))
    else:
        checks.append(Check("Node.js 20+", False, "not found", "Install Node.js 20 LTS or newer from nodejs.org"))
    try:
        c = sqlite3.connect(":memory:")
        c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        checks.append(Check("SQLite FTS5", True, sqlite3.sqlite_version))
    except sqlite3.Error:
        checks.append(Check("SQLite FTS5", False, "missing", "Use the official Python build from python.org (it includes FTS5)"))

    cache = s.model_cache_dir
    have_models = cache.exists() and any(cache.rglob("*.onnx"))
    checks.append(
        Check("Embedding/reranker models downloaded", have_models, str(cache), "Run: npm run setup (downloads ~100 MB once; needs internet)", blocking=False)
    )

    if s.db_path.exists():
        try:
            from bisense.retrieval.index import get_index

            idx = get_index(force=True)
            checks.append(Check("Search index", True, f"{idx.dataset_mode} dataset, version {idx.version}, {idx.counts.get('chunks')} chunks"))
        except Exception as exc:  # noqa: BLE001 - report any index problem
            checks.append(Check("Search index", False, str(exc)[:120], "Run: npm run ingest"))
    else:
        checks.append(Check("Search index", False, "data/index/bisense.db not found", "Run: npm run ingest"))

    public = s.data_dir / "public"
    n_public = len([p for p in public.glob("*") if p.suffix in (".html", ".pdf")]) if public.exists() else 0
    checks.append(
        Check(
            "Official BIS pages (Tier B)", n_public > 0, f"{n_public} files in data/public", "Run: npm run fetch-public (needs internet, once)", blocking=False
        )
    )
    raw = s.data_dir / "raw"
    n_raw = len(list(raw.glob("*.pdf"))) if raw.exists() else 0
    checks.append(
        Check("Real Indian Standards (Tier A)", True, f"{n_raw} PDFs in data/raw" + ("" if n_raw else " (demo pack is used instead)"), blocking=False)
    )

    if s.llm_provider == "none" or not s.llm_configured:
        checks.append(
            Check(
                "LLM",
                True,
                "not configured: answers use extractive mode (verbatim clauses)",
                "Optional: add a free key in .env (see .env.example)",
                blocking=False,
            )
        )
    else:
        from bisense.answer.llm_client import get_llm

        llm = get_llm()
        reach = bool(llm and llm.reachable())
        checks.append(
            Check(
                "LLM reachable",
                reach,
                f"{s.llm_model} at {s.llm_base_url}",
                "Check LLM_BASE_URL / LLM_API_KEY in .env, internet access, or start Ollama. The app still works in extractive mode.",
                blocking=False,
            )
        )

    tess = shutil.which("tesseract")
    checks.append(Check("Tesseract OCR (optional)", True, tess or "not installed (only needed for scanned PDFs)", blocking=False))
    dist = REPO_ROOT / "web" / "dist" / "index.html"
    checks.append(Check("Web app built", dist.exists(), "web/dist" if dist.exists() else "not built", "Run: npm run build", blocking=False))
    return checks


def download_models(log=print) -> None:
    from bisense.retrieval.embed import embed_query
    from bisense.retrieval.rerank import rerank

    s = get_settings()
    log(f"Downloading/checking embedding model {s.embedding_model} ...")
    embed_query("model check")
    log(f"Downloading/checking reranker {s.reranker_model} ...")
    rerank("model check", ["passage"])
    from bisense.voice import stt_mode

    if stt_mode(s) == "local":
        from bisense.voice.stt import load_local_model

        log(f"Downloading/checking local speech-to-text model (Whisper {s.stt_local_model}, ~460 MB once) ...")
        try:
            load_local_model(s)
        except Exception as exc:  # voice is optional; typing always works
            log(f"  could not prepare local speech-to-text ({type(exc).__name__}); the microphone will use the browser instead")
    log(f"Models ready in {s.model_cache_dir}")


def run_warm(log=print) -> dict:
    """Run the demo arc through the live pipeline; results land in the answer cache as 'warmed'."""
    from bisense.answer import cache
    from bisense.answer.ask import run_ask
    from bisense.answer.compare import run_compare
    from bisense.answer.llm_client import get_llm
    from bisense.models import AskContext, AskRequest
    from bisense.retrieval.index import db_conn

    spec = yaml.safe_load((REPO_ROOT / "docs" / "demo_questions.yaml").read_text(encoding="utf-8"))
    if get_llm() is None:
        log("No LLM configured: warming stores nothing (extractive answers need no cache). Add a key in .env first.")
        return {"warmed": 0}
    cache.WARMING = True
    settings = get_settings()
    old_demo = settings.demo_mode
    settings.demo_mode = True  # live pipeline first (never short-circuit on an existing cache entry)
    summary = {"ok": 0, "extractive": 0, "refused": 0, "items": []}
    try:
        for item in spec.get("questions", []):
            t0 = time.perf_counter()
            ctx = item.get("context")
            req = AskRequest(query=item["q"], lang=item.get("lang", "en"), context=AskContext(**ctx) if ctx else None)
            answer = None
            for ev, data in run_ask(req):
                if ev == "answer":
                    answer = data
            mode = answer.mode if answer else "none"
            kind = answer.answer_type if answer else "none"
            summary["items"].append({"q": item["q"], "mode": mode, "answer_type": kind})
            if mode == "extractive":
                summary["extractive"] += 1
            elif kind == "insufficient_evidence":
                summary["refused"] += 1
            else:
                summary["ok"] += 1
            log(f"  {item['q'][:70]:70} -> {kind} ({mode}) {time.perf_counter() - t0:.1f}s")
            time.sleep(3)  # stay under free-tier rate limits (e.g. Groq: 30 requests/minute)
        for slug in spec.get("summaries", []):
            t0 = time.perf_counter()
            req = AskRequest(
                query=f"Explain {slug_label(slug)} in simple language.",
                lang="en",
                context=AskContext(open_slug=slug, focus_slugs=[slug], recent_questions=["summary"]),
            )
            for ev, data in run_ask(req):
                if ev == "answer":
                    log(f"  summary {slug} -> {data.answer_type} ({data.mode}) {time.perf_counter() - t0:.1f}s")
        conn = db_conn()
        try:
            for a, b in spec.get("compare_pairs", []):
                t0 = time.perf_counter()
                resp = run_compare(conn, a, b, "en")
                log(f"  compare {a} vs {b} -> {resp.mode} {time.perf_counter() - t0:.1f}s")
        finally:
            conn.close()
    finally:
        cache.WARMING = False
        settings.demo_mode = old_demo
    return summary


def slug_label(slug: str) -> str:
    from bisense.retrieval.index import db_conn

    conn = db_conn()
    try:
        r = conn.execute("SELECT number_canonical, title FROM standards WHERE slug = ?", (slug,)).fetchone()
        return (r["number_canonical"] or r["title"]) if r else slug
    finally:
        conn.close()
