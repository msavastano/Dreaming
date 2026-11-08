import json
from types import SimpleNamespace

from google.genai import types

from lorekeeper import gm
from lorekeeper.config import load_config
from lorekeeper.llm import Budgeted, ClaudeProvider, GeminiProvider, Message, UsageLog
from lorekeeper.memory import NotesStore, _search_simple, format_note, search, Hit
from lorekeeper.play import Campaign, Game
from lorekeeper.transcript import Transcript

from test_core import FakeProvider, reply_json


class NullMeter:
    def __init__(self):
        self.calls = 0

    def before_call(self):
        pass

    def after_call(self, model, usage):
        self.calls += 1


# --- notes -----------------------------------------------------------------

def test_notes_round_trip(tmp_path):
    store = NotesStore(tmp_path / "notes")
    a = store.add("Wren's beloved is named Mary.", ["Wren", "Mary"], turn="s004-t0002")
    b = store.add("  Sela saw   Wren's face was grey. ", [], turn="s001-t0001")
    assert (a.id, b.id) == ("n0001", "n0002")
    notes = store.all()
    assert [n.text for n in notes] == ["Wren's beloved is named Mary.", "Sela saw Wren's face was grey."]
    assert notes[0].about == ("Wren", "Mary") and notes[0].turn == "s004-t0002"
    assert notes[0].status == "unverified"
    assert format_note(notes[0]) == "[n0001, from s004-t0002, unverified] Wren's beloved is named Mary. (about: Wren, Mary)"


# --- search ----------------------------------------------------------------

def test_search_finds_old_turns_and_notes(tmp_path):
    t = Transcript(tmp_path / "transcripts")
    t.append("I knock on the gatehouse door", "Sela asks why your face is so grey.", None)
    for i in range(30):
        t.append(f"I wait {i}", "Rain falls on the thatch.", None)
    notes = NotesStore(tmp_path / "notes")
    notes.add("Ferris says Maren never goes to the Greywood edge.", ["Ferris", "Maren"], "s002-t0005")

    hits = search(tmp_path / "transcripts", notes, "Sela grey face")
    assert hits and hits[0].id == "s001-t0001"
    hits = search(tmp_path / "transcripts", notes, "Maren")
    assert hits[0].kind == "note"
    assert search(tmp_path / "transcripts", notes, "dragon") == []
    assert search(tmp_path / "transcripts", notes, "  ") == []


def test_simple_search_fallback():
    docs = [Hit("a", "turn", "the grey wolf"), Hit("b", "turn", "grey grey sky"), Hit("c", "turn", "blue")]
    assert [h.id for h in _search_simple(docs, ["grey"], 5)] == ["b", "a"]


# --- reply parsing ---------------------------------------------------------

def test_structured_reply_becomes_changes():
    turn = gm.parse_reply(reply_json(
        "You pay.", copper_delta=-2, location="Inn, upstairs",
        stash=[{"place": "inn room", "items": ["short sword"]}],
        set_flags=[{"name": "promised_creature", "value": "true"}, {"name": "mood", "value": "tired"}],
    ))
    assert turn.parse_error is None
    assert turn.state_change == {
        "location": "Inn, upstairs", "copper_delta": -2,
        "stash": {"inn room": ["short sword"]},
        "set_flags": {"promised_creature": True, "mood": "tired"},
    }
    assert gm.parse_reply(reply_json("Nothing happens.")).state_change == {}


def test_cut_off_json_keeps_the_narration():
    turn = gm.parse_reply('{"narration": "You open the \\"old\\" door and')
    assert turn.narration == 'You open the "old" door and'
    assert turn.state_change is None and turn.parse_error


def test_old_fenced_replies_still_work():
    turn = gm.parse_reply('Rain.\n```state\n{"copper_delta": 3}\n```')
    assert turn.narration == "Rain." and turn.state_change == {"copper_delta": 3}


def _walk_objects(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for v in schema.values():
            yield from _walk_objects(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _walk_objects(v)


def test_schemas_are_strict():
    """Strict tools and structured outputs need closed objects with every field required."""
    for schema in [gm.REPLY_SCHEMA] + [t.schema for t in gm.TOOLS]:
        for obj in _walk_objects(schema):
            assert obj["additionalProperties"] is False
            assert sorted(obj["required"]) == sorted(obj["properties"])


# --- the game loop with tools ----------------------------------------------

def test_remember_and_search_during_a_turn(tmp_path):
    campaign = Campaign(tmp_path / "camp")
    provider = FakeProvider([
        [("remember", {"fact": "Wren's beloved is named Mary.", "about": ["Wren", "Mary"]})],
        reply_json("Hobb nods at your story."),
        [("search_memory", {"query": "Mary beloved"})],
        reply_json("You remember Mary."),
    ])
    game = Game(campaign, Budgeted(provider, campaign.usage, 100_000), "RULES", load_config(None))

    turn = game.take_turn("I tell a story about Mary, my beloved")
    assert turn.narration == "Hobb nods at your story."
    assert turn.tool_calls[0]["result"] == "Saved as n0001."
    note = campaign.notes.all()[0]
    assert note.turn == "s001-t0001"  # cites the turn it came from

    turn = game.take_turn("Who is my beloved?")
    assert "Mary" in turn.tool_calls[0]["result"]
    # The second prompt carries the note.
    last_message = provider.calls[1][1][-1].text
    assert "<notes>" in last_message and "Wren's beloved is named Mary." in last_message

    # Each model call is logged, including tool rounds.
    assert campaign.usage.totals()["calls"] == 4
    records = [json.loads(l) for l in (campaign.transcripts / "s001.jsonl").read_text().splitlines()]
    assert records[0]["tools"][0]["name"] == "remember"


def test_unknown_or_empty_tool_calls_are_harmless(tmp_path):
    campaign = Campaign(tmp_path / "camp")
    game = Game(campaign, Budgeted(FakeProvider([]), campaign.usage, 1), "RULES", load_config(None))
    assert "Unknown tool" in game.run_tool("fly", {})
    assert "Nothing saved" in game.run_tool("remember", {"fact": " ", "about": []})
    assert campaign.notes.all() == []


# --- provider tool loops, with fake API clients ----------------------------

def _claude_response(content, stop_reason):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


def test_claude_loop_runs_tools_then_answers():
    tool_use = SimpleNamespace(type="tool_use", id="tu_1", name="remember", input={"fact": "x", "about": []})
    final = SimpleNamespace(type="text", text=reply_json("Done."))
    responses = [_claude_response([tool_use], "tool_use"), _claude_response([final], "end_turn")]
    sent = []

    def create(**kwargs):
        sent.append(kwargs)
        return responses.pop(0)

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    provider.model, provider.effort = "claude-haiku-5-5", "low"
    meter = NullMeter()
    reply = provider.complete("SYS", [Message("user", "hi")], 500, meter, tools=gm.TOOLS,
                              tool_handler=lambda n, a: "Saved as n0001.", schema=gm.REPLY_SCHEMA)

    assert json.loads(reply.text)["narration"] == "Done."
    assert reply.calls == 2 and meter.calls == 2 and reply.input_tokens == 20
    assert reply.stop_reason == "end_turn"
    assert reply.tool_calls == [{"name": "remember", "args": {"fact": "x", "about": []}, "result": "Saved as n0001."}]
    assert sent[0]["output_config"]["format"]["type"] == "json_schema"
    assert all(t["strict"] for t in sent[0]["tools"])
    second = sent[1]["messages"]
    assert second[-1]["content"][0] == {"type": "tool_result", "tool_use_id": "tu_1", "content": "Saved as n0001."}


def test_claude_last_round_disables_tools():
    tool_use = SimpleNamespace(type="tool_use", id="tu", name="search_memory", input={"query": "q"})
    sent = []

    def create(**kwargs):
        sent.append(kwargs)
        if "tool_choice" in kwargs:
            return _claude_response([SimpleNamespace(type="text", text=reply_json("Fine."))], "end_turn")
        return _claude_response([tool_use], "tool_use")

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    provider.model, provider.effort = "m", "low"
    reply = provider.complete("S", [Message("user", "hi")], 500, NullMeter(), tools=gm.TOOLS,
                              tool_handler=lambda n, a: "Nothing found.", schema=gm.REPLY_SCHEMA, max_tool_rounds=2)
    assert len(sent) == 3 and sent[-1]["tool_choice"] == {"type": "none"}
    assert json.loads(reply.text)["narration"] == "Fine."


def _gemini_response(parts):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=4, thoughts_token_count=2, cached_content_token_count=6),
    )


def test_gemini_loop_runs_tools_then_answers():
    call = types.Part(function_call=types.FunctionCall(name="search_memory", args={"query": "Mary"}))
    responses = [_gemini_response([call]), _gemini_response([types.Part(text=reply_json("Mary waits."))])]
    sent = []

    def generate_content(model, contents, config):
        sent.append((list(contents), config))
        return responses.pop(0)

    provider = GeminiProvider.__new__(GeminiProvider)
    provider.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    provider.model, provider.thinking_level = "gemini-3.8-flash", "LOW"
    reply = provider.complete("SYS", [Message("user", "hi")], 500, NullMeter(), tools=gm.TOOLS,
                              tool_handler=lambda n, a: f"found {a['query']}", schema=gm.REPLY_SCHEMA)

    assert json.loads(reply.text)["narration"] == "Mary waits."
    assert reply.calls == 2 and reply.output_tokens == 12 and reply.cached_tokens == 12
    config = sent[0][1]
    assert config.response_mime_type == "application/json" and config.response_json_schema == gm.REPLY_SCHEMA
    assert config.automatic_function_calling.disable is True
    second_contents = sent[1][0]
    assert second_contents[-2].parts[0].function_call.name == "search_memory"  # model turn replayed
    assert second_contents[-1].parts[0].function_response.response == {"result": "found Mary"}


# --- playtest fixes: short flags, phrase ranking ----------------------------

LONG = "Hobb said livestock have vanished from the Greywood edge for three nights."


def test_long_flags_become_notes(tmp_path):
    campaign = Campaign(tmp_path / "camp")
    provider = FakeProvider([reply_json("Hobb leans in.", set_flags=[
        {"name": "room_rented", "value": "true"}, {"name": "hobb_gossip", "value": LONG}])])
    game = Game(campaign, Budgeted(provider, campaign.usage, 100_000), "RULES", load_config(None))
    turn = game.take_turn("I listen")
    assert game.state["flags"] == {"room_rented": True}
    note = campaign.notes.all()[0]
    assert note.text == LONG and note.about == ("hobb gossip",) and note.turn == "s001-t0001"
    assert turn.tool_calls[0]["from_flag"] == "hobb_gossip"


def test_old_long_flags_move_to_notes_on_load(tmp_path):
    campaign = Campaign(tmp_path / "camp")
    state = json.loads(campaign.state_path.read_text())
    state["flags"] = {"met_dask": True, "hobb_gossip": LONG}
    campaign.state_path.write_text(json.dumps(state))
    game = Game(campaign, Budgeted(FakeProvider([]), campaign.usage, 1), "RULES", load_config(None))
    assert game.state["flags"] == {"met_dask": True}
    assert json.loads(campaign.state_path.read_text())["flags"] == {"met_dask": True}
    assert format_note(campaign.notes.all()[0]).startswith("[n0001, from flag hobb_gossip, unverified]")


def test_exact_phrase_ranks_first(tmp_path):
    t = Transcript(tmp_path / "transcripts")
    t.append("I go to the inn", "It reminds you of a childhood song, Magic Lantern.", None)
    t.append("I say it came by magic", "Magic is rare and costly, magic leaves marks. Magic.", None)
    t.append("I light a lantern", "The lantern sputters.", None)
    hits = search(tmp_path / "transcripts", NotesStore(tmp_path / "notes"), "magic lantern")
    assert [h.id for h in hits] == ["s001-t0001", "s001-t0002", "s001-t0003"]
    docs = [Hit("a", "turn", "magic magic magic"), Hit("b", "turn", "the magic lantern"), Hit("c", "turn", "a lantern")]
    assert [h.id for h in _search_simple(docs, ["magic", "lantern"], 5)][0] == "b"


def test_recall_finds_the_magic_lantern_song(tmp_path):
    """The test2 playtest: a detail from turn 2 asked about after the window moved on."""
    campaign = Campaign(tmp_path / "camp")
    t = Transcript(campaign.transcripts)
    t.append("where am i", "You stand at the gate of Thornwick. Down the lane is the Crooked Lantern.", {})
    t.append("I go to the Inn. It's name reminds me of song from a Bard from childhood called \"Magic Lantern\"",
             "The name tugs at a memory of a bard's song from your childhood, \"Magic Lantern\".", {})
    t.append("I tell her the letter came to me by magic.", "Maren's eyes narrow at the word magic.", {})
    for i in range(22):
        t.append(f"I wait {i}", "The lamp burns low by Maren's hearth.", {})
    provider = FakeProvider([reply_json("Magic Lantern, you recall.")])
    game = Game(campaign, Budgeted(provider, campaign.usage, 100_000), "RULES", load_config(None))

    turn = game.take_turn("what was the song the inn's name reminded me of?")
    assert turn.recalled[0] == "s001-t0002"
    prompt = provider.calls[0][1][-1].text
    assert "<recalled>" in prompt and "Magic Lantern" in prompt
    # Turns already in the window are not recalled again.
    assert all(i not in turn.recalled for i in ("s001-t0020", "s001-t0025"))


def test_no_recall_for_weak_matches(tmp_path):
    campaign = Campaign(tmp_path / "camp")
    t = Transcript(campaign.transcripts)
    t.append("I eat stew", "The stew is hot.", {})
    for i in range(25):
        t.append(f"I wait {i}", "Rain.", {})
    provider = FakeProvider([reply_json("You walk.")])
    game = Game(campaign, Budgeted(provider, campaign.usage, 100_000), "RULES", load_config(None))
    turn = game.take_turn("I walk to the stew pot by the well")  # only one word matches
    assert turn.recalled == [] and "<recalled>" not in provider.calls[0][1][-1].text
