"""Download Tier B official public documents listed in data/public_sources.yaml.

What: fetches each allow-listed bis.gov.in page (and optional official order PDFs) into
data/public/, and records the URL, retrieval date and sha256 in data/public/fetch_log.yaml.

Why: BIS service information (certification schemes, hallmarking, labs, consumer help) and the
official "products under compulsory certification" lists are public. Indexing them gives real,
citable evidence without bypassing any login.

Rules enforced here: only the listed URLs on official domains, a polite delay between requests,
never follow links discovered inside fetched content. bis.gov.in sometimes drops connections mid-file,
so each file is retried with increasing waits; a file that still fails is skipped (and fetched on the
next run) instead of aborting the rest. Progress is saved after every file.
"""

from __future__ import annotations

import hashlib
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

ALLOWED_HOSTS = {"www.bis.gov.in", "bis.gov.in"}
USER_AGENT = "BISense/0.1 (SIH 2026 prototype; polite research fetcher)"
DELAY_S = 3.0


def load_public_sources(data_dir: Path) -> list[dict]:
    path = data_dir / "public_sources.yaml"
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(raw.get("pages", []))


def load_fetch_log(data_dir: Path) -> dict[str, dict]:
    path = data_dir / "public" / "fetch_log.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


RETRY_WAITS_S = (5.0, 15.0, 30.0)  # waits before the 2nd, 3rd and 4th attempt


class FetchResult(dict):
    """fetch_log entries, plus which files failed this run (`failed`) and which were never attempted."""

    failed: list[str]
    missing: list[str]


def _save_log(out_dir: Path, fetch_log: dict[str, dict]) -> None:
    tmp = out_dir / "fetch_log.yaml.tmp"
    tmp.write_text(yaml.safe_dump(fetch_log, sort_keys=True, allow_unicode=True), encoding="utf-8")
    tmp.replace(out_dir / "fetch_log.yaml")


def _get_with_retries(client: httpx.Client, url: str, log, sleep=time.sleep) -> httpx.Response | None:
    """GET with retries on network errors, 429 and 5xx. Returns None when every attempt failed."""
    for attempt in range(len(RETRY_WAITS_S) + 1):
        if attempt:
            wait = RETRY_WAITS_S[attempt - 1]
            log(f"  retrying in {wait:.0f} s (attempt {attempt + 1} of {len(RETRY_WAITS_S) + 1})")
            sleep(wait)
        try:
            resp = client.get(url)
        except httpx.HTTPError as exc:
            log(f"  network error: {str(exc)[:120]}")
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            log(f"  HTTP {resp.status_code}")
            continue
        return resp
    return None


def fetch_all(data_dir: Path, refresh: bool = False, log=print, sleep=time.sleep, client: httpx.Client | None = None) -> FetchResult:
    """Fetch every listed page that is not already present (or all, with refresh=True)."""
    out_dir = data_dir / "public"
    out_dir.mkdir(parents=True, exist_ok=True)
    fetch_log = load_fetch_log(data_dir)
    entries = load_public_sources(data_dir)
    failed: list[str] = []

    own = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)
    try:
        todo = [e for e in entries if refresh or e["file"] not in fetch_log or not (out_dir / e["file"]).exists()]
        for n, entry in enumerate(todo, start=1):
            url, file_name = entry["url"], entry["file"]
            host = urlparse(url).hostname or ""
            if host not in ALLOWED_HOSTS:
                log(f"skip (host not allowed): {url}")
                continue
            if n > 1:
                sleep(DELAY_S)
            log(f"[{n}/{len(todo)}] GET {url}")
            resp = _get_with_retries(client, url, log, sleep)
            if resp is None:
                log(f"  skipped for now: {file_name} (will be tried again next run)")
                failed.append(file_name)
                continue
            if resp.status_code != 200:
                log(f"  skipped: HTTP {resp.status_code} for {file_name}")
                failed.append(file_name)
                continue
            final_host = urlparse(str(resp.url)).hostname or ""
            if final_host not in ALLOWED_HOSTS:
                log(f"  skipped: redirected off the official domain to {resp.url}")
                failed.append(file_name)
                continue
            target = out_dir / file_name
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(resp.content)
            tmp.replace(target)
            fetch_log[file_name] = {
                "url": url,
                "obtained_on": date.today().isoformat(),
                "sha256": hashlib.sha256(resp.content).hexdigest(),
                "bytes": len(resp.content),
            }
            _save_log(out_dir, fetch_log)  # progress survives Ctrl+C or a crash
    finally:
        if own:
            client.close()

    _save_log(out_dir, fetch_log)
    result = FetchResult(fetch_log)
    result.failed = failed
    result.missing = [e["file"] for e in entries if e["file"] not in fetch_log]
    return result
