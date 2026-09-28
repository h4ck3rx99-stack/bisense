"""HTTP API via TestClient: happy paths, validation errors, 404s, rate limit, SSE, headers."""


def test_health_and_library(client):
    h = client.get("/api/health").json()
    assert h["status"] in ("ok", "degraded") and h["dataset_mode"] == "sample"
    assert h["counts"]["standards_full_text"] == 4
    lib = client.get("/api/library").json()
    assert lib["counts"]["chunks"] > 50 and lib["categories"]


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_standards_list_filters_and_suggest(client):
    r = client.get("/api/standards", params={"kind": "standard", "q": "helmet"}).json()
    assert r["total"] == 1 and r["items"][0]["slug"] == "demo-201-2026" and r["items"][0]["synthetic"] is True
    assert client.get("/api/standards", params={"page_size": 1000}).status_code == 422
    assert client.get("/api/standards", params={"kind": "evil"}).status_code == 422
    s = client.get("/api/standards/suggest", params={"q": "DEMO-10"}).json()
    assert {x["slug"] for x in s} >= {"demo-101-2026", "demo-102-2026"}


def test_standard_detail_clause_requirements_csv(client):
    d = client.get("/api/standards/demo-101-2026").json()
    assert d["summary"]["number"] == "DEMO-101:2026" and d["amendments"] and d["scope_text"]
    assert d["compulsory"]["status"] == "unknown"
    c = client.get("/api/standards/demo-101-2026/clauses/4.3.1").json()
    assert "250 ml" in c["text"]
    t = client.get("/api/standards/demo-101-2026/clauses/Table 1").json()
    assert "500" in t["text"] and t["is_table"]
    assert client.get("/api/standards/demo-101-2026/clauses/99.9").status_code == 404
    reqs = client.get("/api/standards/demo-101-2026/requirements", params={"modality": "shall"}).json()
    assert reqs["items"] and all(i["modality"] == "shall" for i in reqs["items"])
    csv = client.get("/api/standards/demo-101-2026/requirements.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    assert "study aid, not a certification" in csv.text and "Synthetic demo data" in csv.text


def test_not_found_and_bad_slugs(client):
    assert client.get("/api/standards/nope").status_code == 404
    assert client.get("/api/standards/..%2F..%2Fetc").status_code == 404
    assert client.get("/api/nope").status_code == 404


def test_search_validation_and_results(client):
    assert client.post("/api/search", json={"query": ""}).status_code == 422
    assert client.post("/api/search", json={"query": "x" * 1001}).status_code == 422
    assert client.post("/api/search", json={"query": "ok", "lang": "fr"}).status_code == 422
    r = client.post("/api/search", json={"query": "coliform bacteria in drinking water"}).json()
    assert r["citations"][0]["standard_number"].startswith("DEMO-")
    assert r["citations"][0]["synthetic"] is True


def test_ask_streams_events_in_order(client, fake_llm):
    with client.stream("POST", "/api/ask", json={"query": "What is the maximum mass of a two-wheeler helmet?"}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert events[0] == "stage"
    assert events.index("evidence") < events.index("answer") < events.index("done")


def test_page_image_and_compare(client, fake_llm):
    png = client.get("/api/standards/demo-101-2026/pages/2.png", params={"q": "Coliform bacteria"})
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    assert client.get("/api/standards/demo-101-2026/pages/99.png").status_code == 404
    cmp = client.post("/api/compare", json={"a": "demo-101-2026", "b": "demo-102-2026"}).json()
    assert {r["aspect"] for r in cmp["rows"]} >= {"Scope", "Requirements", "Test methods"}
    tds = [n for n in cmp["numeric"] if n["parameter"].lower().startswith("total dissolved")]
    assert tds and tds[0]["a_value"] == "500" and tds[0]["b_value"] == "150 to 700"
    assert client.post("/api/compare", json={"a": "demo-101-2026", "b": "demo-101-2026"}).status_code == 422


def test_rate_limit(client):
    from bisense.api import ask as ask_api
    from bisense.api.common import RateLimiter

    old = ask_api._ask_limiter
    ask_api._ask_limiter = RateLimiter("2/minute")
    try:
        codes = [client.post("/api/compare", json={"a": "demo-101-2026", "b": "demo-102-2026"}).status_code for _ in range(3)]
        assert codes[-1] == 429
    finally:
        ask_api._ask_limiter = old


def test_debug_trace_disabled_by_default(client):
    assert client.get("/api/debug/trace/abc").status_code == 404


def test_health_reports_unavailable_reranker_with_a_fix(client, monkeypatch):
    from bisense.retrieval import rerank

    monkeypatch.setattr(rerank, "_model", None)
    monkeypatch.setattr(rerank, "_load_error", "ValueError: download blocked")
    h = client.get("/api/health").json()
    assert h["status"] == "degraded"
    assert h["retrieval"]["reranker"] == "unavailable" and "npm run setup" in h["retrieval"]["fix"]
    # search still works without it
    r = client.post("/api/search", json={"query": "helmet mass", "lang": "en"})
    assert r.status_code == 200 and r.json()["citations"]
