"""Application settings.

All configuration comes from environment variables (or a `.env` file at the repository root),
read once through pydantic-settings. Every variable is documented in `.env.example`.

Why: one typed place for configuration means no scattered `os.getenv` calls, and a missing or
malformed value fails loudly at startup instead of deep inside a request.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# server/bisense/config.py -> repository root is two levels above the package directory.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    demo_mode: bool = False

    # official (default) | sample (adds the Tier D sample pack; see docs/DATA.md)
    dataset: str = "official"
    data_dir: Path = REPO_ROOT / "data"

    # LLM: any OpenAI-compatible chat endpoint. "fake" is used by tests; "none" forces extractive.
    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_alt_model: str = ""  # optional second model on the same provider (used when the first is rate-limited)
    llm_fallback_base_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""
    llm_timeout_s: float = 20.0
    llm_max_tokens: int = 1200

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    rerank_enabled: bool = True
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    model_cache_dir: Path = REPO_ROOT / "data" / "models"
    # ONNX intra-op threads per model at query time. Two models (embedder + reranker) with all cores
    # each contend badly; 2 threads each measured fastest on a 16-core laptop (see docs/DECISIONS.md).
    onnx_threads: int = 2

    top_k_context: int = 8
    context_token_budget: int = 3000

    # Gate thresholds (calibrated by `bisense eval`, see docs/EVAL.md).
    gate_rerank_min: float = -4.0
    gate_rerank_min_no_llm: float = 1.0
    strength_strong_min: float = 3.0
    strength_moderate_min: float = 0.0
    # If the LLM declines but the best passage scores at least this, show verbatim passages instead.
    llm_refusal_override_min: float = 5.0

    languages: str = "en,hi,kn"
    translation_provider: str = "llm"
    # Optional separate model (same provider/key) for translating answers; empty = the answering model.
    translation_model: str = ""
    # Voice (server side; keys never reach the browser). Provider "auto" uses Groq when a Groq key is
    # available (STT_API_KEY, or LLM_API_KEY when LLM_BASE_URL is Groq); "none" disables the server
    # provider and the browser's own speech features are used where they exist.
    stt_provider: str = "auto"  # auto | openai_compatible | none
    stt_base_url: str = "https://api.groq.com/openai/v1"
    stt_api_key: str = ""
    stt_model: str = "whisper-large-v3-turbo"
    stt_fallback_model: str = "whisper-large-v3"
    stt_timeout_s: float = 30.0
    stt_max_bytes: int = 8_000_000
    stt_max_seconds: int = 60
    tts_provider: str = "auto"  # auto | openai_compatible | none
    tts_base_url: str = "https://api.groq.com/openai/v1"
    tts_api_key: str = ""
    tts_model: str = "canopylabs/orpheus-v1-english"
    tts_voice: str = "hannah"
    tts_languages: str = "en"  # languages the configured TTS model can speak
    tts_timeout_s: float = 30.0

    rate_limit_ask: str = "20/minute"
    allow_uploads: bool = False
    cors_origins: str = "http://localhost:5173"

    def model_post_init(self, __context: object) -> None:
        # Relative paths in .env ("./data") mean "relative to the repository root", wherever the
        # command is run from (the CLI and server run inside server/).
        if not self.data_dir.is_absolute():
            self.data_dir = (REPO_ROOT / self.data_dir).resolve()
        if not self.model_cache_dir.is_absolute():
            self.model_cache_dir = (REPO_ROOT / self.model_cache_dir).resolve()

    # ---- derived paths -------------------------------------------------
    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def db_path(self) -> Path:
        return self.index_dir / "bisense.db"

    @property
    def language_list(self) -> list[str]:
        return [x.strip() for x in self.languages.split(",") if x.strip()]

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "fake":
            return True
        return bool(self.llm_base_url and self.llm_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
