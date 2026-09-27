"""Test fixtures.

`built_index` builds a small, isolated index from the synthetic demo pack in a temporary data directory
(the real data/index is never touched) with LLM_PROVIDER=fake, so tests need no network and no API key.
The embedding/reranker models are read from the normal model cache (downloaded by `npm run setup`).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def built_index(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    shutil.copytree(REPO / "data" / "demo", data / "demo")
    os.environ["DATA_DIR"] = str(data)
    os.environ["MODEL_CACHE_DIR"] = str(REPO / "data" / "models")
    os.environ["LLM_PROVIDER"] = "fake"
    os.environ["DATASET"] = "demo"
    os.environ["DEMO_MODE"] = "false"
    os.environ["RATE_LIMIT_ASK"] = "1000/minute"
    os.environ["BISENSE_NO_WARMUP"] = "1"

    from bisense.config import get_settings

    get_settings.cache_clear()
    from bisense.answer.llm_client import set_llm
    from bisense.ingest.pipeline import run_ingest
    from bisense.retrieval import index as index_mod

    set_llm(None, override=False)
    report = run_ingest(get_settings(), dataset="demo", log=lambda *_: None)
    index_mod.get_index(force=True)
    yield {"data_dir": data, "report": report}


@pytest.fixture()
def fake_llm(built_index):
    from bisense.answer.llm_client import FakeLLM, set_llm
    from bisense.retrieval import search as search_mod

    llm = FakeLLM()
    set_llm(llm)
    search_mod._cache.clear()
    yield llm
    set_llm(None, override=False)


@pytest.fixture()
def client(built_index):
    from fastapi.testclient import TestClient

    from bisense.main import create_app

    with TestClient(create_app()) as c:
        yield c
