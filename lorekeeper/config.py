"""Loads config.toml into a plain dict, with defaults for anything missing."""

from __future__ import annotations

import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "narration": {"provider": "gemini", "max_output_tokens": 2000, "window_turns": 20, "window_step": 10,
                  "max_tool_rounds": 3, "notes_in_prompt": 40, "tools": True,
                  "recall_hits": 3, "recall_chars": 400},
    "gemini": {"model": "gemini-3.8-flash", "thinking_level": "LOW"},
    "claude": {"model": "claude-haiku-5-5", "effort": "low"},
    "dream": {"provider": "claude", "effort": "medium", "thinking_level": "MEDIUM", "min_turns": 10,
              "chunk_turns": 25, "max_output_tokens": 16000, "cast_limit": 60, "on_quit": True},
    "budget": {"daily_token_cap": 600_000},
}


def load_config(path: Path | None = None) -> dict:
    config = {section: dict(values) for section, values in DEFAULTS.items()}
    if path is not None and path.exists():
        with path.open("rb") as f:
            for section, values in tomllib.load(f).items():
                config.setdefault(section, {}).update(values)
    return config
