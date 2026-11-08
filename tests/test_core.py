import json
from pathlib import Path

import pytest

from lorekeeper import gm
from lorekeeper.config import load_config
from lorekeeper.llm import Budgeted, BudgetExceeded, Message, Reply, UsageLog
from lorekeeper.play import Campaign, Game, ROOT
from lorekeeper.state import apply_changes
from lorekeeper.transcript import Transcript, load_recent_turns

BASE_STATE = {
    "hero": {"name": "Wren", "hp": 10, "max_hp": 12},
    "location": "gate",
    "gold": 5,
    "inventory": ["rope", "torch"],
    "flags": {},
}


class FakeProvider:
    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, messages, max_tokens):
        self.calls.append((system, messages))
        return Reply(text=self.replies.pop(0), model="fake-1", input_tokens=100, output_tokens=50)


# --- state -----------------------------------------------------------------

def test_apply_changes_clamps_and_updates():
    new = apply_changes(BASE_STATE, {
        "hp_delta": 99, "gold_delta": -50, "location": "inn",
        "add_items": ["key"], "remove_items": ["torch", "not-held"],
        "set_flags": {"met_hobb": True},
    })
    assert new["hero"]["hp"] == 12  # capped at max
    assert new["gold"] == 0  # never negative
    assert new["location"] == "inn"
    assert new["inventory"] == ["rope", "key"]
    assert new["flags"] == {"met_hobb": True}
    assert BASE_STATE["inventory"] == ["rope", "torch"]  # original untouched


def test_apply_changes_ignores_bad_values():
    new = apply_changes(BASE_STATE, {"hp_delta": "lots", "add_items": "sword", "location": "  ", "junk": 1})
    assert new == BASE_STATE


# --- reply parsing ---------------------------------------------------------

def test_parse_reply_with_state_block():
    text = 'You enter the inn.\n\n```state\n{"location": "inn", "gold_delta": -1}\n```\n'
    turn = gm.parse_reply(text)
    assert turn.narration == "You enter the inn."
    assert turn.state_change == {"location": "inn", "gold_delta": -1}
    assert turn.parse_error is None


def test_parse_reply_without_block_and_with_bad_json():
    assert gm.parse_reply("Rain falls.").state_change is None
    bad = gm.parse_reply("Rain.\n```state\n{oops}\n```")
    assert bad.state_change is None and bad.parse_error
    assert bad.narration == "Rain."


# --- prompt building -------------------------------------------------------

def test_build_messages_keeps_history_first_and_state_last():
    recent = [{"player": "look", "narration": "A gate."}]
    msgs = gm.build_messages(recent, BASE_STATE, "open gate")
    assert [m.role for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0].text == "look"
    assert "<game_state>" in msgs[-1].text and msgs[-1].text.endswith("Player: open gate")


def test_system_prompt_holds_rules_and_canon():
    system = gm.build_system("RULES", "CANON")
    assert system.startswith("RULES") and "<canon>\nCANON\n</canon>" in system


# --- transcripts -----------------------------------------------------------

def test_transcript_ids_and_sessions(tmp_path):
    t1 = Transcript(tmp_path)
    assert t1.append("a", "A", None)["id"] == "s001-t0001"
    assert t1.append("b", "B", {"gold_delta": 1})["id"] == "s001-t0002"
    t2 = Transcript(tmp_path)  # a new session
    assert t2.append("c", "C", None)["id"] == "s002-t0001"
    recent = load_recent_turns(tmp_path, 2)
    assert [r["player"] for r in recent] == ["b", "c"]
    assert [r["player"] for r in load_recent_turns(tmp_path, 10)] == ["a", "b", "c"]


# --- usage and budget ------------------------------------------------------

def test_budget_blocks_calls_over_the_cap(tmp_path):
    usage = UsageLog(tmp_path / "usage.jsonl")
    llm = Budgeted(FakeProvider(["one", "two"]), usage, daily_cap=150)
    llm.complete("s", [Message("user", "hi")], 10, purpose="narrate")
    assert usage.tokens_today() == 150
    with pytest.raises(BudgetExceeded):
        llm.complete("s", [Message("user", "hi")], 10, purpose="narrate")
    assert usage.totals()["calls"] == 1


# --- a full turn, end to end -----------------------------------------------

def test_game_turn_updates_state_and_transcript(tmp_path):
    campaign = Campaign(tmp_path / "camp")
    assert (campaign.folder / "canon.md").exists()  # created from the template
    provider = FakeProvider([
        'Hobb waves you in.\n```state\n{"location": "The Crooked Lantern", "gold_delta": -2}\n```',
        "The fire crackles.",
    ])
    config = load_config(None)
    game = Game(campaign, Budgeted(provider, campaign.usage, 10_000), "RULES", config)
    start_gold = game.state["gold"]

    turn = game.take_turn("enter the inn")
    assert turn.narration == "Hobb waves you in."
    saved = json.loads(campaign.state_path.read_text())
    assert saved["location"] == "The Crooked Lantern"
    assert saved["gold"] == start_gold - 2

    game.take_turn("sit by the fire")
    _, messages = provider.calls[1]
    # The second prompt replays the first turn before the new move.
    assert messages[0].text == "enter the inn"
    assert messages[1].text == "Hobb waves you in."
    assert "Thornwick" in provider.calls[1][0]  # canon is in the system prompt

    lines = (campaign.transcripts / "s001.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert campaign.usage.totals()["calls"] == 2


def test_repo_config_and_prompt_load():
    config = load_config(ROOT / "config.toml")
    assert config["gemini"]["model"] == "gemini-3.8-flash"
    assert config["claude"]["model"] == "claude-haiku-5-5"
    assert "```state" in gm.load_rules(ROOT / "prompts")
