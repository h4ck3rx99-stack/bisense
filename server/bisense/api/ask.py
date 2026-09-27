"""POST /api/search (retrieval only, fast) and POST /api/ask (Server-Sent Events).

SSE event order for /api/ask:
    stage -> query -> stage -> evidence -> [stage drafting -> stage verifying -> stage translating]
    -> answer -> trace -> done           (or `error` at any point)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from bisense.answer.ask import run_ask
from bisense.answer.present import query_info, to_citation, to_standard_ref
from bisense.api.common import ApiError, RateLimiter, get_db
from bisense.config import get_settings
from bisense.models import AskRequest, SearchRequest, SearchResponse
from bisense.retrieval.index import IndexMissing
from bisense.retrieval.query import ClientContext, understand
from bisense.retrieval.search import search

router = APIRouter(prefix="/api", tags=["ask"])
log = logging.getLogger("bisense.api")
_ask_limiter = RateLimiter(get_settings().rate_limit_ask)


@router.post("/search", response_model=SearchResponse)
def search_endpoint(req: SearchRequest, conn: sqlite3.Connection = Depends(get_db)) -> SearchResponse:
    ctx = req.context
    plan = understand(
        conn,
        req.query,
        ui_lang=req.lang,
        context=ClientContext(
            recent_questions=list(ctx.recent_questions) if ctx else [],
            focus_slugs=list(ctx.focus_slugs) if ctx else [],
            open_slug=ctx.open_slug if ctx else None,
        ),
    )
    # Instant results: no cross-encoder (it costs ~1-2 s on a laptop CPU); /api/ask reranks.
    res = search(conn, plan, rerank_enabled=False)
    cands = res.context
    if req.filters and req.filters.kinds:
        cands = [c for c in cands if c.std_kind in req.filters.kinds]
    for i, c in enumerate(cands, start=1):
        c.citation_id = c.citation_id or f"C{i}"
    return SearchResponse(
        query=query_info(plan),
        citations=[to_citation(c, i) for i, c in enumerate(cands, start=1)],
        standards=[to_standard_ref(h) for h in res.standards[:10]],
        timings=res.timings,
        total_candidates=len(res.candidates),
    )


def _sse(event: str, data: BaseModel | dict) -> str:
    payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/ask")
def ask_endpoint(req: AskRequest, request: Request) -> StreamingResponse:
    _ask_limiter.check(request)
    request_id = uuid.uuid4().hex[:12]

    def stream() -> Iterator[str]:
        t0 = time.perf_counter()
        info: dict = {"route": "/api/ask", "lang": req.lang}
        try:
            for event, data in run_ask(req):
                if event == "answer":
                    info.update(mode=data.mode, provider=data.provider, answer_type=data.answer_type, dropped=data.dropped_count)  # type: ignore[union-attr]
                if event == "query":
                    info["intent"] = data.intent  # type: ignore[union-attr]
                if event == "trace":
                    info["timings"] = data.timings.stages  # type: ignore[union-attr]
                    info["tokens"] = data.tokens  # type: ignore[union-attr]
                    info["request_id"] = data.request_id  # type: ignore[union-attr]
                yield _sse(event, data)
        except IndexMissing:
            yield _sse("error", {"code": "no_index", "message_key": "error.no_index"})
        except Exception:  # never leak a stack trace to the client
            log.exception("ask failed")
            yield _sse("error", {"code": "internal", "message_key": "error.internal"})
            yield _sse("done", {"request_id": request_id, "timings": {"stages": {}, "total_ms": 0}})
        finally:
            info["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            log.info(json.dumps(info, ensure_ascii=False))

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def check_rate(request: Request) -> None:
    _ask_limiter.check(request)


__all__ = ["router", "ApiError", "check_rate"]
