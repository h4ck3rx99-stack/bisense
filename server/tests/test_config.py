"""Every variable in .env.example must be a real setting (a renamed or invented name would be silently ignored)."""

import re
from pathlib import Path

from bisense.config import Settings

REPO = Path(__file__).resolve().parents[2]


def test_env_example_names_match_settings():
    documented = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", (REPO / ".env.example").read_text(encoding="utf-8"), re.M))
    fields = {name.upper() for name in Settings.model_fields}
    assert documented - fields == set(), f"unknown variables in .env.example: {sorted(documented - fields)}"
