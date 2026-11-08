"""Loads config.toml into a plain dict, with defaults for anything missing."""

from __future__ import annotations

import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "narration": {"provider": "gemini", "max_output_tokens": 1200, "window_turns": 20},
    "gemini": {"model": "gemini-3.8-flash", "thinking_level": "LOW"},
    "claude": {"model": "claude-haiku-5-5", "effort": "low"},
    "budget": {"daily_token_cap": 300_000},
}


def load_config(path: Path | None = None) -> dict:
    config = {section: dict(values) for section, values in DEFAULTS.items()}
    if path is not None and path.exists():
        with path.open("rb") as f:
            for section, values in tomllib.load(f).items():
                config.setdefault(section, {}).update(values)
    return config
