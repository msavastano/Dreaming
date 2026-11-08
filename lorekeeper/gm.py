"""The game master: builds each turn's prompt and reads the reply.

Prompt layout, ordered so the start stays the same turn to turn (cache-friendly):
  system   = GM rules + canon.md          (stable)
  messages = the last N turns              (grows by one turn each move)
  last msg = current state + player move   (changes every turn)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .llm import Message

STATE_BLOCK = re.compile(r"```state\s*\n(.*?)```", re.DOTALL)


@dataclass
class Turn:
    narration: str
    state_change: dict | None
    parse_error: str | None = None


def build_system(rules: str, canon: str) -> str:
    return f"{rules.strip()}\n\n<canon>\n{canon.strip()}\n</canon>\n"


def build_messages(recent_turns: list[dict], state: dict, player_move: str) -> list[Message]:
    messages: list[Message] = []
    for turn in recent_turns:
        messages.append(Message("user", turn["player"]))
        messages.append(Message("assistant", turn["narration"]))
    current = (
        f"<game_state>\n{json.dumps(state, sort_keys=True)}\n</game_state>\n\n"
        f"Player: {player_move}"
    )
    messages.append(Message("user", current))
    return messages


def parse_reply(text: str) -> Turn:
    """Split the narration from the optional ```state block."""
    matches = list(STATE_BLOCK.finditer(text))
    narration = STATE_BLOCK.sub("", text).strip()
    if not matches:
        return Turn(narration=narration, state_change=None)
    raw = matches[-1].group(1).strip()
    try:
        change = json.loads(raw)
    except json.JSONDecodeError as e:
        return Turn(narration=narration, state_change=None, parse_error=f"bad state JSON: {e}")
    if not isinstance(change, dict):
        return Turn(narration=narration, state_change=None, parse_error="state block was not an object")
    return Turn(narration=narration, state_change=change)


def load_rules(prompts_dir: Path) -> str:
    return (prompts_dir / "gm.md").read_text()
