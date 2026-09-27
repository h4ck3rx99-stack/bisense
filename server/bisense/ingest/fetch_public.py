"""Download Tier B official public documents listed in data/public_sources.yaml.

What: fetches each allow-listed bis.gov.in page (and optional official order PDFs) into
data/public/, and records the URL, retrieval date and sha256 in data/public/fetch_log.yaml.

Why: BIS service information (certification schemes, hallmarking, labs, consumer help) and the
official "products under compulsory certification" lists are public. Indexing them gives real,
citable evidence without bypassing any login.

Rules enforced here: only the listed URLs on official domains, a polite delay between requests,
stop on the first HTTP error, never follow links discovered inside fetched content.
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


def fetch_all(data_dir: Path, refresh: bool = False, log=print) -> dict[str, dict]:
    """Fetch every listed page that is not already present (or all, with refresh=True)."""
    out_dir = data_dir / "public"
    out_dir.mkdir(parents=True, exist_ok=True)
    fetch_log = load_fetch_log(data_dir)
    entries = load_public_sources(data_dir)

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=40, follow_redirects=True) as client:
        first = True
        for entry in entries:
            url, file_name = entry["url"], entry["file"]
            host = urlparse(url).hostname or ""
            if host not in ALLOWED_HOSTS:
                log(f"skip (host not allowed): {url}")
                continue
            target = out_dir / file_name
            if target.exists() and file_name in fetch_log and not refresh:
                continue
            if not first:
                time.sleep(DELAY_S)
            first = False
            log(f"GET {url}")
            try:
                resp = client.get(url)
            except httpx.HTTPError as exc:
                log(f"stopping: network error for {url}: {exc}")
                break
            if resp.status_code != 200:
                log(f"stopping: HTTP {resp.status_code} for {url}")
                break
            final_host = urlparse(str(resp.url)).hostname or ""
            if final_host not in ALLOWED_HOSTS:
                log(f"stopping: redirected off official domain to {resp.url}")
                break
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(resp.content)
            tmp.replace(target)
            fetch_log[file_name] = {
                "url": url,
                "obtained_on": date.today().isoformat(),
                "sha256": hashlib.sha256(resp.content).hexdigest(),
                "bytes": len(resp.content),
            }

    (out_dir / "fetch_log.yaml").write_text(
        yaml.safe_dump(fetch_log, sort_keys=True, allow_unicode=True), encoding="utf-8"
    )
    return fetch_log
