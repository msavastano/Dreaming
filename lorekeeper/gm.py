"""The game master: builds each turn's prompt, defines its tools, reads its reply.

Prompt layout, ordered so the start stays the same turn to turn (cache-friendly):
  system   = GM rules + canon.md          (stable)
  messages = recent turns                  (start moves in steps, see transcript.window_start)
  last msg = notes + current state + move  (changes every turn)

The reply is JSON matching REPLY_SCHEMA, which both providers enforce, so the
state update can't be skipped. Older fenced ```state replies still parse.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .llm import Message, ToolSpec

STATE_BLOCK = re.compile(r"```state\s*\n(.*?)```", re.DOTALL)

_STRINGS = {"type": "array", "items": {"type": "string"}}

REPLY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "narration": {"type": "string", "description": "What happens, told to the player."},
        "state": {
            "type": "object",
            "description": "What changed this turn. Use empty values for anything unchanged.",
            "properties": {
                "location": {"type": "string", "description": "Where the hero is now if they moved, else empty."},
                "copper_delta": {"type": "integer", "description": "Money gained (+) or spent (-), in copper."},
                "hp_delta": {"type": "integer", "description": "Healing (+) or damage (-)."},
                "add_items": {**_STRINGS, "description": "Items the hero now carries."},
                "remove_items": {**_STRINGS, "description": "Carried items used up, lost or given away."},
                "stash": {
                    "type": "array",
                    "description": "Carried items the hero leaves somewhere.",
                    "items": {
                        "type": "object",
                        "properties": {"place": {"type": "string"}, "items": _STRINGS},
                        "required": ["place", "items"],
                        "additionalProperties": False,
                    },
                },
                "retrieve": {**_STRINGS, "description": "Stored items the hero picks back up."},
                "set_flags": {
                    "type": "array",
                    "description": "Facts the game should track: promises, deals, quests, lasting conditions.",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                        "required": ["name", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": [
                "location", "copper_delta", "hp_delta", "add_items", "remove_items",
                "stash", "retrieve", "set_flags",
            ],
            "additionalProperties": False,
        },
    },
    "required": ["narration", "state"],
    "additionalProperties": False,
}

TOOLS = [
    ToolSpec(
        name="remember",
        description=(
            "Save one fact to long-term memory so it survives after this turn scrolls out of view. "
            "Save what the game state can't show: names, relationships, promises, secrets, what a "
            "character claimed (and who said it), clues, contradictions between characters, and "
            "anything the player tells you about the hero's past. One specific fact per call."
        ),
        schema={
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact, in one or two plain sentences."},
                "about": {**_STRINGS, "description": "Names of the characters, places or things it concerns."},
            },
            "required": ["fact", "about"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="search_memory",
        description=(
            "Search saved notes and every earlier turn of the campaign, including turns you can no "
            "longer see. Use it when the player or a character refers to something earlier than the "
            "turns in front of you, or before you describe a character, place or event that may have "
            "come up before."
        ),
        schema={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A few key words, such as names."}},
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
]


@dataclass
class Turn:
    narration: str
    state_change: dict | None
    parse_error: str | None = None
    tool_calls: list[dict] = field(default_factory=list)


def build_system(rules: str, canon: str) -> str:
    return f"{rules.strip()}\n\n<canon>\n{canon.strip()}\n</canon>\n"


def build_messages(recent_turns: list[dict], state: dict, player_move: str, notes: list[str] | None = None) -> list[Message]:
    messages: list[Message] = []
    for turn in recent_turns:
        messages.append(Message("user", turn["player"]))
        messages.append(Message("assistant", turn["narration"]))
    parts = []
    if notes:
        parts.append("<notes>\n" + "\n".join(notes) + "\n</notes>")
    parts.append(f"<game_state>\n{json.dumps(state, sort_keys=True)}\n</game_state>")
    parts.append(f"Player: {player_move}")
    messages.append(Message("user", "\n\n".join(parts)))
    return messages


def parse_reply(text: str) -> Turn:
    """Read a JSON reply (the normal case), or fall back to a fenced ```state block."""
    data = _load_json_object(text)
    if data is not None and isinstance(data.get("narration"), str):
        state = data.get("state")
        if not isinstance(state, dict):
            return Turn(narration=data["narration"].strip(), state_change=None, parse_error="no state in reply")
        return Turn(narration=data["narration"].strip(), state_change=structured_to_changes(state))
    if STATE_BLOCK.search(text) or not text.lstrip().startswith("{"):
        return _parse_fenced(text)
    # Broken JSON, usually cut off by the output limit: rescue the narration.
    match = re.search(r'"narration"\s*:\s*"((?:[^"\\]|\\.)*)', text)
    narration = json.loads(f'"{match.group(1)}"') if match else text
    return Turn(narration=narration.strip(), state_change=None, parse_error="reply was not valid JSON")


def structured_to_changes(state: dict) -> dict:
    """Turn the schema's flat, all-fields-present shape into apply_changes() input."""
    changes: dict = {}
    if isinstance(state.get("location"), str) and state["location"].strip():
        changes["location"] = state["location"].strip()
    for key in ("copper_delta", "hp_delta"):
        if state.get(key):
            changes[key] = state[key]
    for key in ("add_items", "remove_items", "retrieve"):
        if state.get(key):
            changes[key] = state[key]
    stash: dict[str, list[str]] = {}
    for entry in state.get("stash") or []:
        if isinstance(entry, dict) and entry.get("place") and entry.get("items"):
            stash.setdefault(entry["place"], []).extend(entry["items"])
    if stash:
        changes["stash"] = stash
    flags = {}
    for entry in state.get("set_flags") or []:
        if isinstance(entry, dict) and entry.get("name"):
            flags[entry["name"]] = _flag_value(entry.get("value", ""))
    if flags:
        changes["set_flags"] = flags
    return changes


def _flag_value(value):
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return value


def _load_json_object(text: str) -> dict | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _parse_fenced(text: str) -> Turn:
    matches = list(STATE_BLOCK.finditer(text))
    narration = STATE_BLOCK.sub("", text).strip()
    if not matches:
        return Turn(narration=narration, state_change=None, parse_error="no state block")
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
