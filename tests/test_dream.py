import json

from lorekeeper.checks import quote_found
from lorekeeper.config import load_config
from lorekeeper.dream import DREAM_SCHEMA, dream, load_dream_state, split_canon, undreamed_turns
from lorekeeper.llm import Budgeted
from lorekeeper.play import Campaign, Game
from lorekeeper.transcript import Transcript
from lorekeeper.wiki import Fact, Page, WikiStore, parse_page

from test_core import FakeProvider, reply_json
from test_memory import _walk_objects

TAM_TURN = ("I go to the boy and ask him if he can lead me to Maren",
            "Inside, a freckled boy of perhaps twelve sits on an upturned bucket. \"Name's Tam.\"")


def dream_json(pages=(), notes=(), story="Wren reached Thornwick.", threads=("Deliver the letter.",), recap="You arrived."):
    return json.dumps({"pages": list(pages), "notes": list(notes), "story_so_far": story,
                       "open_threads": list(threads), "recap": recap})


def tam_page(**extra):
    page = {"name": "Tam", "kind": "person", "aliases": [], "summary": "Freckled boy of about twelve, Hobb's stable boy.",
            "facts": [{"text": "Tam is a freckled boy of about twelve.", "turn": "s001-t0001",
                       "quote": "a freckled boy of perhaps twelve"}],
            "contradictions": []}
    page.update(extra)
    return page


def setup(tmp_path, turns=(TAM_TURN,), steps=()):
    campaign = Campaign(tmp_path / "camp")
    t = Transcript(campaign.transcripts)
    for player, narration in turns:
        t.append(player, narration, {})
    provider = FakeProvider(list(steps))
    config = load_config(None)
    return campaign, provider, Budgeted(provider, campaign.usage, 100_000), config


def test_wiki_page_round_trip(tmp_path):
    store = WikiStore(tmp_path / "wiki")
    page = Page("Tam", "person", "Freckled boy.", ["Tam Hollis"],
                [Fact("Tam is twelve.", "s001-t0008", "perhaps twelve")], ["s001-t0008 vs s002-t0005"], "s001-t0008")
    store.save(page)
    back = store.find("tam hollis")
    assert back == page and parse_page(page.render()) == page
    assert page.mentioned_in("I ask Tam about it") and not page.mentioned_in("Tamsin waves")


def test_quote_check():
    source = 'Inside, a freckled boy of perhaps twelve sits on an upturned bucket.'
    assert quote_found("a freckled boy of perhaps twelve", source)
    assert quote_found("freckled boy, of perhaps twelve!", source)        # punctuation
    assert quote_found("a freckled boy of perhaps twelve sits on a bucket", source)  # small slip in the middle
    assert not quote_found("a weathered man with a scar", source)
    assert not quote_found("twelve", source)                               # too short to check


def test_dream_schema_is_strict():
    for obj in _walk_objects(DREAM_SCHEMA):
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])


def test_dream_writes_pages_checks_notes_and_canon(tmp_path):
    invented = {"text": "Tam is secretly a prince.", "turn": "s001-t0001", "quote": "Tam is a hidden prince of Ashford"}
    steps = [dream_json(
        pages=[tam_page(facts=tam_page()["facts"] + [invented])],
        notes=[{"id": "n0001", "verdict": "wrong", "correction": "Tam is about twelve."}],
    )]
    campaign, provider, llm, config = setup(tmp_path, steps=steps)
    campaign.notes.add("Tam is an old man.", ["Tam"], "s001-t0001")

    result = dream(campaign, llm, "DREAM RULES", config, force=True)

    page = campaign.wiki.find("Tam")
    assert [f.text for f in page.facts] == ["Tam is a freckled boy of about twelve."]
    assert result.dropped == ["Tam: Tam is secretly a prince."]
    assert campaign.notes.all()[0].status == "wrong"
    assert campaign.notes.all()[0].correction == "Tam is about twelve."
    canon = campaign.canon_path.read_text()
    assert "- Tam (person): Freckled boy of about twelve, Hobb's stable boy." in canon
    assert "## World rules" in canon  # sections dreaming doesn't own are kept
    assert "Wren reached Thornwick." in canon
    assert (campaign.folder / "canon.prev.md").exists() and "+- Tam (person)" in result.canon_diff
    assert load_dream_state(campaign) | {"last_dream": ""} == {"dreamed_turns": 1, "recap": "You arrived.", "last_dream": ""}
    assert undreamed_turns(campaign) == []
    # The model was shown the turns and the note.
    prompt = provider.calls[0][1][0].text
    assert "[s001-t0001]" in prompt and "[n0001, from s001-t0001] Tam is an old man." in prompt
    assert campaign.usage.totals()["calls"] == 1


def test_dream_skips_short_sessions_unless_forced(tmp_path):
    campaign, provider, llm, config = setup(tmp_path, steps=[dream_json()])
    assert dream(campaign, llm, "R", config) is None
    assert dream(campaign, llm, "R", config, force=True) is not None
    assert dream(campaign, llm, "R", config, force=True) is None  # nothing new left


def test_contradiction_reaches_canon_and_old_pages_are_shown(tmp_path):
    later = ("who are you, I say", "A thin, weathered jaw. \"Name's Tam, Tam Hollis.\"")
    contradiction = "s001-t0001 calls Tam a boy of about twelve; s001-t0002 describes a weathered man."
    campaign, provider, llm, config = setup(tmp_path, turns=(TAM_TURN, later), steps=[
        dream_json(pages=[tam_page()]),
        dream_json(pages=[tam_page(aliases=["Tam Hollis"], contradictions=[contradiction])]),
    ])
    config["dream"]["chunk_turns"] = 1  # two chunks, one call each
    result = dream(campaign, llm, "R", config, force=True)
    assert result.calls == 2 and result.new_pages == ["Tam"] and result.updated_pages == ["Tam"]
    # The second call saw the page the first call wrote.
    assert "<wiki>\n---\nname: Tam" in provider.calls[1][1][0].text
    canon = campaign.canon_path.read_text()
    assert "## Contradictions to keep straight" in canon and contradiction in canon
    assert campaign.wiki.find("Tam Hollis").name == "Tam"


def test_pages_the_model_did_not_see_keep_their_facts(tmp_path):
    campaign, provider, llm, config = setup(tmp_path, turns=[("I wait", "Rain on the roof of the inn.")], steps=[
        dream_json(pages=[{"name": "Hobb", "kind": "person", "aliases": [], "summary": "Halfling innkeeper.",
                           "facts": [{"text": "It rains on the inn.", "turn": "s001-t0001", "quote": "Rain on the roof"}],
                           "contradictions": []}])])
    campaign.wiki.save(Page("Hobb", "person", "Innkeeper.", [], [Fact("Hobb runs the inn.", "s000-t0001", "")]))
    dream(campaign, llm, "R", config, force=True)
    assert [f.text for f in campaign.wiki.find("Hobb").facts] == ["Hobb runs the inn.", "It rains on the inn."]


def test_game_uses_dreamed_memory(tmp_path):
    campaign, provider, llm, config = setup(tmp_path, steps=[dream_json(pages=[tam_page()])])
    campaign.notes.add("Tam is a boy.", ["Tam"], "s001-t0001")
    campaign.notes.add("Hobb owes Wren a favor.", ["Hobb"], "s001-t0001")
    dream(campaign, llm, "R", config, force=True)  # the fake gives no verdict for n0002, so it stays unchecked
    campaign.notes.set_status("n0001", "confirmed")

    play = FakeProvider([reply_json("Tam waves.")])
    game = Game(campaign, Budgeted(play, campaign.usage, 100_000), "RULES", config)
    game.take_turn("I wave at Tam the freckled boy")
    system, messages = play.calls[0]
    assert "- Tam (person): Freckled boy" in system          # cast is in the cached system prompt
    notes_block = messages[-1].text.split("</notes>")[0]
    assert "Hobb owes Wren a favor." in notes_block and "Tam is a boy." not in notes_block  # only unchecked notes


def test_output_limit_is_reported_and_changes_nothing(tmp_path):
    import pytest
    from lorekeeper.dream import DreamError
    from lorekeeper.llm import Reply, Usage

    class OutOfRoom:
        name = "fake"

        def complete(self, system, messages, max_tokens, meter, **kwargs):
            meter.before_call()
            meter.after_call("fake-1", Usage(9000, 8000, 0))
            return Reply(text="", model="fake-1", input_tokens=9000, output_tokens=8000, stop_reason="max_tokens")

    campaign, _, _, config = setup(tmp_path)
    with pytest.raises(DreamError, match="ran out of output room"):
        dream(campaign, Budgeted(OutOfRoom(), campaign.usage, 100_000), "R", config, force=True)
    assert len(undreamed_turns(campaign)) == 1 and campaign.wiki.all() == []


def test_a_chunk_that_runs_out_of_room_is_split_in_half(tmp_path):
    from lorekeeper.llm import Reply, Usage

    class RoomForThree:
        """Runs out of room on more than three turns."""
        name = "fake"

        def __init__(self):
            self.sizes = []

        def complete(self, system, messages, max_tokens, meter, **kwargs):
            meter.before_call()
            meter.after_call("fake-1", Usage(9000, 800, 0))
            size = messages[0].text.count("\nPlayer: ")
            self.sizes.append(size)
            if size > 3:
                return Reply(text="", model="fake-1", input_tokens=9000, output_tokens=800, stop_reason="max_tokens")
            return Reply(text=dream_json(), model="fake-1", input_tokens=9000, output_tokens=800)

    turns = [(f"I wait {i}", f"Time passes {i}.") for i in range(6)]
    campaign, _, _, config = setup(tmp_path, turns=turns)
    campaign.notes.add("A note from a flag.", ["Wren"], "flag")
    provider = RoomForThree()
    result = dream(campaign, Budgeted(provider, campaign.usage, 100_000), "R", config, force=True)
    assert provider.sizes == [6, 3, 3] and result.splits == 1 and result.calls == 3
    assert undreamed_turns(campaign) == []
