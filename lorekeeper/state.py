"""Game state that code owns: hit points, money, location, items and flags.

The model never edits this file directly. It proposes changes in a `state`
block, and apply_changes() checks and applies them. Keeping this out of memory
follows the article's lesson: store in memory only what the screen can't show.

Money is one number of copper pieces: 1 gold = 10 silver = 100 copper.
Items are either carried (`inventory`) or stored at a named place (`stored`).
"""

from __future__ import annotations

import json
from pathlib import Path

COPPER_PER_SILVER = 10
COPPER_PER_GOLD = 100


def load_state(path: Path) -> dict:
    return upgrade_state(json.loads(path.read_text()))


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def upgrade_state(state: dict) -> dict:
    """Bring a state saved by an older version up to date."""
    if "copper" not in state:
        state["copper"] = int(state.pop("gold", 0)) * COPPER_PER_GOLD
    state.setdefault("inventory", [])
    state.setdefault("stored", {})
    state.setdefault("flags", {})
    return state


def format_money(copper: int) -> str:
    gold, rest = divmod(copper, COPPER_PER_GOLD)
    silver, copper = divmod(rest, COPPER_PER_SILVER)
    parts = [f"{gold}g"] if gold else []
    if silver:
        parts.append(f"{silver}s")
    if copper or not parts:
        parts.append(f"{copper}c")
    return " ".join(parts)


def apply_changes(state: dict, changes: dict) -> dict:
    """Return a new state with the changes applied. Unknown keys are ignored."""
    new = upgrade_state(json.loads(json.dumps(state)))  # deep copy
    hero = new.setdefault("hero", {"name": "Hero", "hp": 10, "max_hp": 10})

    hp_delta = _as_int(changes.get("hp_delta"))
    if hp_delta:
        hero["hp"] = max(0, min(hero["max_hp"], hero["hp"] + hp_delta))

    copper_delta = _as_int(changes.get("copper_delta"))
    copper_delta += _as_int(changes.get("gold_delta")) * COPPER_PER_GOLD  # older prompt wording
    if copper_delta:
        new["copper"] = max(0, new["copper"] + copper_delta)

    location = changes.get("location")
    if isinstance(location, str) and location.strip():
        new["location"] = location.strip()

    carried = new["inventory"]
    stored = new["stored"]

    for item in _as_list(changes.get("remove_items")):
        if item in carried:
            carried.remove(item)
    for item in _as_list(changes.get("add_items")):
        carried.append(item)

    # {"stash": {"room at the Crooked Lantern": ["short sword"]}} puts carried items down.
    stash = changes.get("stash")
    if isinstance(stash, dict):
        for place, items in stash.items():
            if not isinstance(place, str) or not place.strip():
                continue
            for item in _as_list(items):
                if item in carried:
                    carried.remove(item)
                    stored.setdefault(place.strip(), []).append(item)

    # {"retrieve": ["short sword"]} picks stored items back up, wherever they are.
    for item in _as_list(changes.get("retrieve")):
        for place in list(stored):
            if item in stored[place]:
                stored[place].remove(item)
                carried.append(item)
                if not stored[place]:
                    del stored[place]
                break

    flags = changes.get("set_flags")
    if isinstance(flags, dict):
        new["flags"].update(flags)

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
