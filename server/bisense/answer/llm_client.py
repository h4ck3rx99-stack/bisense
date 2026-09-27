"""One small client for any OpenAI-compatible chat endpoint (Groq, Gemini, OpenRouter, Ollama, ...).

  - primary provider, then fallback provider (both from env), each with a timeout;
  - JSON mode requested where supported; JSON is also extracted robustly from plain text;
  - the model gets NO tools and NO function calling;
  - API keys are never logged or returned to clients.

`FakeLLM` (LLM_PROVIDER=fake) is used by tests: it returns scripted responses and can be made to
"obey" prompt injections so tests can prove the validator catches the consequences.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from bisense.config import Settings, get_settings


class LLMUnavailable(Exception):
    """No provider configured, or every provider failed. The caller falls back to extractive mode."""


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str


def providers_from_settings(s: Settings) -> list[Provider]:
    out = []
    if s.llm_base_url and s.llm_model:
        out.append(Provider("primary", s.llm_base_url.rstrip("/"), s.llm_api_key, s.llm_model))
    if s.llm_fallback_base_url and s.llm_fallback_model:
        out.append(Provider("fallback", s.llm_fallback_base_url.rstrip("/"), s.llm_fallback_api_key, s.llm_fallback_model))
    return out


def extract_json(text: str) -> dict:
    """Parse a JSON object from model output (handles ```json fences, <think> blocks, leading prose)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    raise ValueError("no JSON object found in model output")


class LLMClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.providers = providers_from_settings(self.settings)
        self._down_until: dict[str, float] = {}

    @property
    def configured(self) -> bool:
        return bool(self.providers)

    def chat(self, messages: list[dict], json_mode: bool = True, max_tokens: int | None = None, temperature: float = 0.1) -> LLMResult:
        if not self.providers:
            raise LLMUnavailable("no LLM provider configured")
        errors = []
        for p in self.providers:
            if self._down_until.get(p.name, 0) > time.monotonic():
                errors.append(f"{p.name}: recently failed")
                continue
            try:
                return self._call(p, messages, json_mode, max_tokens or self.settings.llm_max_tokens, temperature)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                # Remember the failure briefly so a dead provider does not add a timeout to every request.
                self._down_until[p.name] = time.monotonic() + 30
                errors.append(f"{p.name}: {exc.__class__.__name__}")
        raise LLMUnavailable("; ".join(errors))

    def _call(self, p: Provider, messages: list[dict], json_mode: bool, max_tokens: int, temperature: float) -> LLMResult:
        body: dict = {"model": p.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if "11434" in p.base_url or "ollama" in p.base_url:
            body["reasoning_effort"] = "none"  # local reasoning models: skip hidden thinking tokens
        headers = {"Content-Type": "application/json"}
        if p.api_key:
            headers["Authorization"] = f"Bearer {p.api_key}"
        t0 = time.perf_counter()
        with httpx.Client(timeout=self.settings.llm_timeout_s) as client:
            resp = client.post(f"{p.base_url}/chat/completions", json=body, headers=headers)
            if resp.status_code == 400 and json_mode:
                # some providers reject response_format; retry once without it
                body.pop("response_format", None)
                resp = client.post(f"{p.base_url}/chat/completions", json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        usage = data.get("usage") or {}
        return LLMResult(
            text=data["choices"][0]["message"]["content"] or "",
            provider=p.name,
            model=p.model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    def reachable(self) -> bool:
        """Cheap reachability check for /api/health and `bisense doctor` (lists models)."""
        for p in self.providers:
            try:
                headers = {"Authorization": f"Bearer {p.api_key}"} if p.api_key else {}
                r = httpx.get(f"{p.base_url}/models", headers=headers, timeout=4)
                if r.status_code < 500:
                    return True
            except httpx.HTTPError:
                continue
        return False


@dataclass
class FakeLLM:
    """Deterministic stand-in for tests. `responder(messages) -> str` builds each reply."""

    responder: Callable[[list[dict]], str] | None = None
    calls: list[list[dict]] = field(default_factory=list)
    fail: bool = False
    configured: bool = True

    def chat(self, messages: list[dict], json_mode: bool = True, max_tokens: int | None = None, temperature: float = 0.1) -> LLMResult:
        self.calls.append(messages)
        if self.fail:
            raise LLMUnavailable("fake provider failure")
        text = self.responder(messages) if self.responder else json.dumps(default_fake_answer(messages))
        return LLMResult(text=text, provider="fake", model="fake", prompt_tokens=100, completion_tokens=50)

    def reachable(self) -> bool:
        return not self.fail


def default_fake_answer(messages: list[dict]) -> dict:
    """A grounded answer built only from the first source block (quotes its first sentence verbatim)."""
    user = messages[-1]["content"]
    m = re.search(r'<source id="(C\d+)"[^>]*>(.*?)</source>', user, re.S)
    if not m:
        return {"answer_type": "insufficient_evidence", "summary": "", "points": [], "standards": [], "gaps": ["No sources were provided."], "follow_ups": []}
    cid, body = m.group(1), " ".join(m.group(2).split())
    first = re.split(r"(?<=[.;])\s", body)[0][:200]
    return {
        "answer_type": "answer",
        "summary": f"The indexed source addresses this [{cid}].",
        "points": [
            {"kind": "source_fact", "text": f"The source states: {first}", "citations": [cid], "quote": first},
            {"kind": "interpretation", "text": "This appears to be the most relevant provision.", "citations": [cid]},
        ],
        "standards": [],
        "gaps": [],
        "follow_ups": [],
    }


_client: LLMClient | FakeLLM | None = None


def get_llm() -> LLMClient | FakeLLM | None:
    """The configured LLM, or None when running in extractive-only mode."""
    global _client
    s = get_settings()
    if _client is None:
        if s.llm_provider == "fake":
            _client = FakeLLM()
        elif s.llm_provider == "none" or not s.llm_configured:
            return None
        else:
            _client = LLMClient(s)
    return _client


def set_llm(client: LLMClient | FakeLLM | None) -> None:
    """Tests use this to inject a FakeLLM."""
    global _client
    _client = client
