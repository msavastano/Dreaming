import json

from lorekeeper import gm
from lorekeeper.config import load_config
from lorekeeper.eval import SETUPS, grade, report, run_setup
from lorekeeper.llm import Budgeted, Reply, Usage
from lorekeeper.play import ROOT

from test_core import reply_json


class EchoProvider:
    """Narrates a fixed line. A quiz answer repeats everything the game master could see,
    so a fact counts as answered exactly when the prompt held it."""

    name = "fake"

    def __init__(self):
        self.calls = []

    def complete(self, system, messages, max_tokens, meter, tools=None, tool_handler=None, schema=None, max_tool_rounds=3):
        self.calls.append({"tools": [t.name for t in tools or []], "schema": schema, "last": messages[-1].text})
        meter.before_call()
        meter.after_call("fake-1", Usage(1000, 100, 800))
        if schema is gm.ANSWER_SCHEMA:
            seen = system + "\n".join(m.text for m in messages[:-1]) + messages[-1].text.split("(Out of character")[0]
            text = json.dumps({"answer": seen})
        elif schema is gm.REPLY_SCHEMA:
            text = reply_json("The village is quiet.")
        else:  # dream
            text = json.dumps({"pages": [], "notes": [], "story_so_far": "Wren settled in.",
                               "open_threads": [], "recap": "Quiet days."})
        return Reply(text=text, model="fake-1", input_tokens=1000, output_tokens=100, cached_tokens=800)


def small_script():
    moves = ["I tell Hobb I grew up in Saltmere."] + [f"I wait {i}." for i in range(29)]
    return {"name": "tiny", "moves": moves, "quiz_after": [30], "dream_every": 15,
            "key": [{"id": "home", "planted": 1, "q": "Where did Wren grow up?", "needs": [["saltmere"]]},
                    {"id": "magic", "planted": 0, "q": "What happens when someone casts a spell?",
                     "needs": [["tired", "marked"]]}],
            "wrong_note": {"after": 1, "text": "Wren grew up in Ashford.", "about": ["Wren"]}}


def run(tmp_path, setup, provider):
    config = load_config(None)
    return run_setup(setup, small_script(), tmp_path / setup, config, provider,
                     lambda cfg, usage: Budgeted(provider, usage, 10**7), 30, 10**7, log=lambda *a: None)


def test_grade():
    needs = [["three silver", "3 silver"], ["full moon"]]
    assert grade("He owes Hobb 3 silver, due by the next Full Moon.", needs)
    assert not grade("He owes Hobb three silver.", needs)


def test_setup_a_has_no_memory_and_forgets(tmp_path):
    provider = EchoProvider()
    r = run(tmp_path, "A", provider)
    assert r.turns == 30 and not r.stopped
    assert all(c["tools"] == [] for c in provider.calls)
    home = next(a for a in r.answers if a["id"] == "home")
    assert not home["in_view"] and not home["correct"]          # turn 1 has left the window
    assert next(a for a in r.answers if a["id"] == "magic")["correct"]  # canon is always there
    assert r.notes == 0 and r.wrong_note_status == ""
    assert r.usage["narrate"]["calls"] == 30 and r.usage["quiz"]["calls"] == 2 and "dream" not in r.usage


def test_setup_b_plants_the_wrong_note_and_uses_tools(tmp_path):
    provider = EchoProvider()
    r = run(tmp_path, "B", provider)
    assert "remember" in provider.calls[0]["tools"]
    quiz_calls = [c for c in provider.calls if c["schema"] is gm.ANSWER_SCHEMA]
    assert all(c["tools"] == ["search_memory"] for c in quiz_calls)   # no new notes during a quiz
    assert r.wrong_note_status == "unverified" and r.notes == 1
    assert "Wren grew up in Ashford." in quiz_calls[0]["last"]          # the wrong note is in the prompt


def test_setup_c_dreams(tmp_path):
    r = run(tmp_path, "C", EchoProvider())
    assert r.usage["dream"]["calls"] == 2  # turns 15 and 30
    assert "Wren settled in." in (tmp_path / "C" / "canon.md").read_text()


def test_report_lists_every_setup(tmp_path):
    results = [run(tmp_path, s, EchoProvider()) for s in SETUPS]
    text = report(results, small_script(), {"when": "now", "provider": "fake", "dream_provider": "fake", "turns": 30})
    for s, label in SETUPS.items():
        assert f"| {s}. {label} |" in text
    assert "| Where did Wren grow up? |" in text and "B: the planted wrong note ended as **unverified**." in text
