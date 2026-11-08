"""Transcripts: the bottom memory layer, a log of every turn.

Each session is one JSONL file (transcripts/s001.jsonl, s002.jsonl, ...).
Each line is one turn with an id like "s001-t0004", so later layers (notes,
wiki) can cite exactly where a fact came from.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class Transcript:
    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        existing = sorted(self.folder.glob("s*.jsonl"))
        self.session = len(existing) + 1
        self.path = self.folder / f"s{self.session:03d}.jsonl"
        self.turn = 0

    def next_id(self) -> str:
        """The id the next appended turn will get."""
        return f"s{self.session:03d}-t{self.turn + 1:04d}"

    def append(self, player: str, narration: str, state_change: dict | None, tool_calls: list[dict] | None = None) -> dict:
        record = {
            "id": self.next_id(),
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "player": player,
            "narration": narration,
            "state_change": state_change or {},
        }
        if tool_calls:
            record["tools"] = tool_calls
        self.turn += 1
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")
        return record


def load_all_turns(folder: Path) -> list[dict]:
    """Every turn across all sessions, oldest first."""
    if not folder.exists():
        return []
    turns: list[dict] = []
    for path in sorted(folder.glob("s*.jsonl")):
        turns.extend(json.loads(l) for l in path.read_text().splitlines() if l.strip())
    return turns


def window_start(total: int, window: int, step: int) -> int:
    """Index of the first turn to show, so at most `window` turns are shown.

    The start only moves forward `step` turns at a time, instead of by one each
    turn. That keeps the beginning of the prompt identical for `step` turns in
    a row, which is what prompt caching needs. The model sees between
    `window - step` and `window` recent turns.
    """
    if total <= window:
        return 0
    step = max(1, min(step, window))
    return ((total - window) // step + 1) * step


def load_window(folder: Path, window: int, step: int) -> list[dict]:
    turns = load_all_turns(folder)
    return turns[window_start(len(turns), window, step):]


def load_recent_turns(folder: Path, limit: int) -> list[dict]:
    """The last `limit` turns across all sessions, oldest first."""
    if limit <= 0:
        return []
    return load_all_turns(folder)[-limit:]
