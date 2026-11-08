import json

from lorekeeper import gm
from lorekeeper.config import load_config
from lorekeeper.eval import SETUPS, current, grade, report, run_setup
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
    assert r.notes == 0 and r.wrong_note_status == {}
    assert r.usage["narrate"]["calls"] == 30 and r.usage["quiz"]["calls"] == 2 and "dream" not in r.usage


def test_setup_b_plants_the_wrong_note_and_uses_tools(tmp_path):
    provider = EchoProvider()
    r = run(tmp_path, "B", provider)
    assert "remember" in provider.calls[0]["tools"]
    quiz_calls = [c for c in provider.calls if c["schema"] is gm.ANSWER_SCHEMA]
    assert all(c["tools"] == ["search_memory"] for c in quiz_calls)   # no new notes during a quiz
    assert r.wrong_note_status == {"Wren grew up in Ashford.": "unverified"} and r.notes == 1
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
    assert "| Where did Wren grow up? |" in text and 'B: the planted wrong note "Wren grew up in Ashford." ended as **unverified**.' in text


def test_a_failed_dream_does_not_stop_setup_c(tmp_path):
    class DreamsBadly(EchoProvider):
        def complete(self, system, messages, max_tokens, meter, tools=None, tool_handler=None, schema=None, max_tool_rounds=3):
            reply = super().complete(system, messages, max_tokens, meter, tools, tool_handler, schema, max_tool_rounds)
            if schema not in (gm.ANSWER_SCHEMA, gm.REPLY_SCHEMA):
                reply.text = "not json"
            return reply

    r = run(tmp_path, "C", DreamsBadly())
    assert r.turns == 30 and not r.stopped and len(r.answers) == 2
    assert len(r.dream_failures) == 2 and r.dream_failures[0].startswith("turn 15: ")


def test_answers_on_the_state_sheet_are_marked(tmp_path):
    provider = EchoProvider()
    config = load_config(None)
    script = small_script()
    script["moves"][0] = "I tell Hobb I grew up in Saltmere."
    original = provider.complete

    def complete(system, messages, max_tokens, meter, schema=None, **kw):
        reply = original(system, messages, max_tokens, meter, schema=schema, **kw)
        if schema is gm.REPLY_SCHEMA and "Saltmere" in messages[-1].text:
            reply.text = reply_json("Hobb nods.", set_flags=[{"name": "home", "value": "Saltmere"}])
        return reply

    provider.complete = complete
    r = run_setup("A", script, tmp_path / "A", config, provider, None, 30, 10**7, log=lambda *a: None)
    home = next(a for a in r.answers if a["id"] == "home")
    assert home["in_state"] and home["correct"] and not home["in_view"]
    assert r.accuracy(in_view=False, in_state=False) == (0, 0)


def test_grade_forbids_whole_words():
    assert not grade("Tam is a fisherman of forty.", [["tam"]], forbid=["forty"])
    assert grade("Tam is twelve, not a man of fortyish years.", [["twelve"]], forbid=["forty"])


def test_changed_facts_use_the_latest_answer():
    item = {"planted": 5, "needs": [["three silver"]], "changes": [{"at": 52, "needs": [["two silver"]]}]}
    assert current(item, 40) == (5, [["three silver"]], [])
    assert current(item, 80) == (52, [["two silver"]], [])


def harder_script():
    script = small_script()
    script["moves"][5] = "I sell my mule and buy a pony named Ember."
    script["key"] = [
        {"id": "home", "kind": "hero", "planted": 1, "q": "Where did Wren grow up?", "needs": [["saltmere"]]},
        {"id": "mount", "kind": "changed", "planted": 1, "q": "What does Wren ride?", "needs": [["mule"]],
         "changes": [{"at": 6, "needs": [["ember"]]}]},
    ]
    script["probes"] = [{"id": "mount", "turn": 20, "planted": 6, "needs": [["ember"]], "forbid": ["quiet"]},
                        {"id": "home", "turn": 25, "planted": 1, "needs": [["quiet"]]}]
    del script["wrong_note"]
    script["wrong_notes"] = [{"after": 1, "text": "Wren grew up in Ashford.", "about": ["Wren"]},
                             {"after": 2, "text": "Tam is forty.", "about": ["Tam"]}]
    return script


def test_probes_kinds_and_several_wrong_notes(tmp_path):
    config = load_config(None)
    script = harder_script()
    r = run_setup("B", script, tmp_path / "B", config, EchoProvider(), None, 30, 10**7, log=lambda *a: None)
    # EchoProvider narrates "The village is quiet." every turn.
    assert [(p["turn"], p["correct"], p["in_view"]) for p in r.probes] == [(20, False, True), (25, True, False)]
    mount = next(a for a in r.answers if a["id"] == "mount")
    assert mount["kind"] == "changed" and mount["in_view"] is False  # the change at turn 6 is out of view at 30
    assert r.wrong_note_status == {"Wren grew up in Ashford.": "unverified", "Tam is forty.": "unverified"}
    text = report([r], script, {"when": "now", "provider": "fake", "dream_provider": "fake", "turns": 30})
    assert "## By kind of fact" in text and "| Facts that changed |" in text
    assert "## In-play probes" in text and "| 25 | I wait 23. | yes* |" in text


def test_scripts_are_well_formed(tmp_path):
    for path in sorted((ROOT / "evals").glob("*.json")):
        script = json.loads(path.read_text())
        n = len(script["moves"])
        assert all(q <= n for q in script["quiz_after"]), path
        for item in script["key"]:
            assert 0 <= item["planted"] <= n and all(item["planted"] < c["at"] <= n for c in item.get("changes", []))
        for probe in script.get("probes", []):
            assert 0 < probe["planted"] < probe["turn"] <= n, (path, probe)
    # The long script runs end to end.
    script = json.loads((ROOT / "evals" / "thornwick-120.json").read_text())
    r = run_setup("C", script, tmp_path / "C", load_config(None), EchoProvider(),
                  lambda cfg, usage: Budgeted(EchoProvider(), usage, 10**8), 120, 10**8, log=lambda *a: None)
    assert r.turns == 120 and not r.stopped and len(r.probes) == 10 and len(r.wrong_note_status) == 2
    assert len(r.answers) == 3 * len(script["key"])
