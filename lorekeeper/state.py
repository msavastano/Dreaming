"""Game state that code owns: hit points, gold, location, inventory and flags.

The model never edits this file directly. It proposes changes in a `state`
block, and apply_changes() checks and applies them. Keeping this out of memory
follows the article's lesson: store in memory only what the screen can't show.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_state(path: Path) -> dict:
    return json.loads(path.read_text())


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def apply_changes(state: dict, changes: dict) -> dict:
    """Return a new state with the changes applied. Unknown keys are ignored."""
    new = json.loads(json.dumps(state))  # deep copy
    hero = new.setdefault("hero", {"name": "Hero", "hp": 10, "max_hp": 10})

    hp_delta = _as_int(changes.get("hp_delta"))
    if hp_delta:
        hero["hp"] = max(0, min(hero["max_hp"], hero["hp"] + hp_delta))

    gold_delta = _as_int(changes.get("gold_delta"))
    if gold_delta:
        new["gold"] = max(0, new.get("gold", 0) + gold_delta)

    location = changes.get("location")
    if isinstance(location, str) and location.strip():
        new["location"] = location.strip()

    inventory = new.setdefault("inventory", [])
    for item in _as_list(changes.get("remove_items")):
        if item in inventory:
            inventory.remove(item)
    for item in _as_list(changes.get("add_items")):
        inventory.append(item)

    flags = changes.get("set_flags")
    if isinstance(flags, dict):
        new.setdefault("flags", {}).update(flags)

    return new


def _as_int(value) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _as_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]
