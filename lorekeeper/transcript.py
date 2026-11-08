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

    def append(self, player: str, narration: str, state_change: dict | None) -> dict:
        self.turn += 1
        record = {
            "id": f"s{self.session:03d}-t{self.turn:04d}",
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "player": player,
            "narration": narration,
            "state_change": state_change or {},
        }
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")
        return record


def load_recent_turns(folder: Path, limit: int) -> list[dict]:
    """The last `limit` turns across all sessions, oldest first."""
    if limit <= 0 or not folder.exists():
        return []
    turns: list[dict] = []
    for path in sorted(folder.glob("s*.jsonl"), reverse=True):
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        for line in reversed(lines):
            turns.append(json.loads(line))
            if len(turns) >= limit:
                return list(reversed(turns))
    return list(reversed(turns))
