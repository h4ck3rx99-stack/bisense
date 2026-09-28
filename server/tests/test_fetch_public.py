"""The official-data downloader survives dropped connections: retries, skips a bad file, resumes next run."""

from pathlib import Path

import httpx
import yaml

from bisense.ingest.fetch_public import fetch_all


def _setup(tmp: Path) -> Path:
    data = tmp / "data"
    data.mkdir()
    pages = [{"file": f"p{i}.html", "url": f"https://www.bis.gov.in/p{i}"} for i in range(3)]
    (data / "public_sources.yaml").write_text(yaml.safe_dump({"pages": pages}), encoding="utf-8")
    return data


def test_retries_then_skips_and_resumes(tmp_path):
    data = _setup(tmp_path)
    calls: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls[path] = calls.get(path, 0) + 1
        if path == "/p0" and calls[path] == 1:
            raise httpx.RemoteProtocolError("peer closed connection without sending complete message body")
        if path == "/p1":
            return httpx.Response(503)
        return httpx.Response(200, content=f"<html>{path}</html>".encode())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_all(data, log=lambda *_: None, sleep=lambda _s: None, client=client)
    assert set(result) == {"p0.html", "p2.html"}  # p0 recovered on retry; p2 fetched although p1 failed
    assert result.failed == ["p1.html"] and result.missing == ["p1.html"]
    assert calls["/p1"] == 4  # 1 try + 3 retries
    assert (data / "public" / "p2.html").exists()

    # next run: only the missing file is requested
    ok_calls: list[str] = []
    ok = httpx.Client(transport=httpx.MockTransport(lambda r: (ok_calls.append(r.url.path), httpx.Response(200, content=b"ok"))[1]))
    result = fetch_all(data, log=lambda *_: None, sleep=lambda _s: None, client=ok)
    assert ok_calls == ["/p1"] and result.missing == []


def test_never_leaves_the_official_domain(tmp_path):
    data = _setup(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://evil.example")
    (data / "public_sources.yaml").write_text(yaml.safe_dump({"pages": [{"file": "x.html", "url": "https://evil.example/x"}]}), encoding="utf-8")
    result = fetch_all(data, log=lambda *_: None, sleep=lambda _s: None, client=client)
    assert "x.html" not in result
