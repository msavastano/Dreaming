import json
from pathlib import Path

import pytest

from lorekeeper import gm
from lorekeeper.config import load_config
from lorekeeper.llm import Budgeted, BudgetExceeded, Message, Reply, UsageLog
from lorekeeper.play import Campaign, Game, ROOT
from lorekeeper.llm import ClaudeProvider
from lorekeeper.play import format_state
from lorekeeper.state import apply_changes, format_money, upgrade_state
from lorekeeper.transcript import Transcript, load_recent_turns, load_window, window_start

BASE_STATE = {
    "hero": {"name": "Wren", "hp": 10, "max_hp": 12},
    "location": "gate",
    "copper": 500,
    "inventory": ["rope", "torch"],
    "stored": {},
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
        "hp_delta": 99, "copper_delta": -9999, "location": "inn",
        "add_items": ["key"], "remove_items": ["torch", "not-held"],
        "set_flags": {"met_hobb": True},
    })
    assert new["hero"]["hp"] == 12  # capped at max
    assert new["copper"] == 0  # never negative
    assert new["location"] == "inn"
    assert new["inventory"] == ["rope", "key"]
    assert new["flags"] == {"met_hobb": True}
    assert BASE_STATE["inventory"] == ["rope", "torch"]  # original untouched


def test_apply_changes_ignores_bad_values():
    new = apply_changes(BASE_STATE, {"hp_delta": "lots", "add_items": "sword", "location": "  ", "junk": 1})
    assert new == BASE_STATE


# --- reply parsing ---------------------------------------------------------

def test_parse_reply_with_state_block():
    text = 'You enter the inn.\n\n```state\n{"location": "inn", "copper_delta": -2}\n```\n'
    turn = gm.parse_reply(text)
    assert turn.narration == "You enter the inn."
    assert turn.state_change == {"location": "inn", "copper_delta": -2}
    assert turn.parse_error is None


def test_parse_reply_without_block_and_with_bad_json():
    missing = gm.parse_reply("Rain falls.")
    assert missing.state_change is None and missing.parse_error == "no state block"
    empty = gm.parse_reply("Rain falls.\n```state\n{}\n```")
    assert empty.state_change == {} and empty.parse_error is None
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
        'Hobb waves you in.\n```state\n{"location": "The Crooked Lantern", "copper_delta": -2}\n```',
        "The fire crackles.\n```state\n{}\n```",
    ])
    config = load_config(None)
    game = Game(campaign, Budgeted(provider, campaign.usage, 10_000), "RULES", config)
    start_copper = game.state["copper"]

    turn = game.take_turn("enter the inn")
    assert turn.narration == "Hobb waves you in."
    saved = json.loads(campaign.state_path.read_text())
    assert saved["location"] == "The Crooked Lantern"
    assert saved["copper"] == start_copper - 2
    assert game.last_reply.input_tokens == 100

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


# --- money and stored items ------------------------------------------------

def test_format_money():
    assert format_money(800) == "8g"
    assert format_money(798) == "7g 9s 8c"
    assert format_money(5) == "5c"
    assert format_money(0) == "0c"


def test_old_state_with_gold_is_upgraded():
    old = {"hero": {"name": "W", "hp": 1, "max_hp": 1}, "gold": 8, "inventory": []}
    new = upgrade_state(old)
    assert new["copper"] == 800 and "gold" not in new and new["stored"] == {}
    # The older prompt's gold_delta still works, counted as gold pieces.
    assert apply_changes(new, {"gold_delta": -1})["copper"] == 700


def test_stash_and_retrieve_items():
    state = apply_changes(BASE_STATE, {"stash": {"inn room": ["torch", "not-held"]}})
    assert state["inventory"] == ["rope"]
    assert state["stored"] == {"inn room": ["torch"]}
    assert "Left at inn room: torch" in format_state(state)
    back = apply_changes(state, {"retrieve": ["torch"]})
    assert back["inventory"] == ["rope", "torch"] and back["stored"] == {}


# --- the history window ----------------------------------------------------

def test_window_start_moves_in_steps():
    assert window_start(15, 20, 10) == 0
    assert window_start(20, 20, 10) == 0
    # Past the window, the start jumps by whole steps and then holds still.
    assert [window_start(n, 20, 10) for n in (21, 25, 30, 31, 40)] == [10, 10, 20, 20, 30]
    for n in range(21, 80):
        shown = n - window_start(n, 20, 10)
        assert 10 <= shown <= 20


def test_load_window_keeps_prompt_start_stable(tmp_path):
    t = Transcript(tmp_path)
    for i in range(25):
        t.append(f"move {i}", f"story {i}", None)
    first = load_window(tmp_path, 20, 10)
    t.append("move 25", "story 25", None)
    second = load_window(tmp_path, 20, 10)
    assert first[0]["player"] == second[0]["player"] == "move 10"
    assert second[1:len(first)] == first[1:]


def test_claude_marks_end_of_history_for_caching():
    msgs = [Message("user", "a"), Message("assistant", "b"), Message("user", "state + move")]
    out = ClaudeProvider._with_history_cache(msgs)
    assert out[1]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert out[2]["content"] == "state + move"
    assert ClaudeProvider._with_history_cache([Message("user", "only")])[0]["content"] == "only"


def test_prompt_requires_state_block_every_turn():
    rules = gm.load_rules(ROOT / "prompts")
    assert "End every reply" in rules and "copper_delta" in rules and "stash" in rules
