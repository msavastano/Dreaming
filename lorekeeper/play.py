"""Play Lorekeeper in the terminal.

    python -m lorekeeper.play                    # default campaign, Gemini
    python -m lorekeeper.play --campaign quest2  # a second campaign
    python -m lorekeeper.play --provider claude  # narrate with Haiku instead

In-game commands: /state, /notes, /wiki [name], /search <words>, /dream, /usage, /quit
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import gm
from .config import load_config
from .llm import Budgeted, BudgetExceeded, Reply, UsageLog, make_provider
from .memory import NotesStore, format_hits, format_note, search
from .wiki import WikiStore
from .state import apply_changes, format_money, load_state, save_state
from .transcript import Transcript, load_window

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"
MAX_FLAG_CHARS = 60  # longer flag values are facts, so they go to notes instead


class Campaign:
    """A campaign is one folder: canon.md, state.json, transcripts/, notes/, wiki/, usage.jsonl."""

    def __init__(self, folder: Path):
        self.folder = folder
        if not folder.exists():
            folder.mkdir(parents=True)
            shutil.copy(TEMPLATES / "canon.md", folder / "canon.md")
            shutil.copy(TEMPLATES / "state.json", folder / "state.json")
        self.canon_path = folder / "canon.md"
        self.state_path = folder / "state.json"
        self.transcripts = folder / "transcripts"
        self.usage = UsageLog(folder / "usage.jsonl")
        self.notes = NotesStore(folder / "notes")
        self.wiki = WikiStore(folder / "wiki")


class Game:
    def __init__(self, campaign: Campaign, llm: Budgeted, rules: str, config: dict):
        self.campaign = campaign
        self.llm = llm
        self.config = config
        self.state = load_state(campaign.state_path)
        self._move_long_flags_to_notes()
        self.rules = rules
        self.reload_canon()
        self.transcript = Transcript(campaign.transcripts)
        self.last_reply: Reply | None = None

    def reload_canon(self) -> None:
        """Canon is part of the cached system prompt, so it only changes after a dream."""
        self.system = gm.build_system(self.rules, self.campaign.canon_path.read_text())

    def _move_long_flags_to_notes(self) -> None:
        """Campaigns from before flags were kept short: move long flags into notes once."""
        flags = self.state.get("flags", {})
        long = {k: v for k, v in flags.items() if _is_long_flag(v)}
        if not long:
            return
        for name, value in long.items():
            self.campaign.notes.add(value, [_flag_topic(name)], turn=f"flag {name}")
            del flags[name]
        save_state(self.campaign.state_path, self.state)

    def _notes_from_flags(self, changes: dict, turn_id: str) -> list[dict]:
        """Take long flag values out of a state change and save them as notes."""
        flags = changes.get("set_flags") or {}
        calls = []
        for name in [k for k, v in flags.items() if _is_long_flag(v)]:
            value = flags.pop(name)
            note = self.campaign.notes.add(value, [_flag_topic(name)], turn=turn_id)
            calls.append({"name": "remember", "args": {"fact": value, "about": [_flag_topic(name)]},
                          "result": f"Saved as {note.id}.", "from_flag": name})
        if not flags:
            changes.pop("set_flags", None)
        return calls

    def run_tool(self, name: str, args: dict) -> str:
        if name == "remember":
            fact = str(args.get("fact", "")).strip()
            if not fact:
                return "Nothing saved: the fact was empty."
            about = [str(a) for a in args.get("about", []) if isinstance(a, str)]
            note = self.campaign.notes.add(fact, about, turn=self.transcript.next_id())
            return f"Saved as {note.id}."
        if name == "search_memory":
            hits = search(self.campaign.transcripts, self.campaign.notes, str(args.get("query", "")),
                          wiki=self.campaign.wiki)
            return format_hits(hits)
        return f"Unknown tool {name!r}."

    def _prompt(self, move: str):
        """The messages for one move, plus what recall found. Shared by play and the eval quiz."""
        cfg = self.config["narration"]
        recent = load_window(self.campaign.transcripts, cfg["window_turns"], cfg["window_step"])
        # Dreamed notes live on in the wiki and canon, so only unchecked ones go in the prompt.
        unchecked = [n for n in self.campaign.notes.all() if n.status == "unverified"]
        shown_notes = unchecked[-cfg["notes_in_prompt"]:] if cfg["notes_in_prompt"] > 0 else []
        notes = [format_note(n) for n in shown_notes]
        recalled = []
        if cfg["recall_hits"] > 0:
            # Free and local: look up the player's words in everything the prompt leaves out.
            seen = {t["id"] for t in recent} | {n.id for n in shown_notes}
            recalled = search(self.campaign.transcripts, self.campaign.notes, move,
                              limit=cfg["recall_hits"], exclude=seen, min_terms=2, wiki=self.campaign.wiki)
        messages = gm.build_messages(recent, self.state, move, notes,
                                     format_hits(recalled, cfg["recall_chars"]) if recalled else None)
        return messages, recalled

    def take_turn(self, move: str) -> gm.Turn:
        cfg = self.config["narration"]
        messages, recalled = self._prompt(move)
        reply = self.llm.complete(
            self.system,
            messages,
            cfg["max_output_tokens"],
            purpose="narrate",
            tools=gm.TOOLS if cfg["tools"] else None,
            tool_handler=self.run_tool,
            schema=gm.REPLY_SCHEMA,
            max_tool_rounds=cfg["max_tool_rounds"],
        )
        self.last_reply = reply
        turn = gm.parse_reply(reply.text)
        turn.tool_calls = list(reply.tool_calls)
        turn.recalled = [h.id for h in recalled]
        if turn.state_change:
            turn.tool_calls += self._notes_from_flags(turn.state_change, self.transcript.next_id())
        if turn.state_change:
            self.state = apply_changes(self.state, turn.state_change)
            save_state(self.campaign.state_path, self.state)
        self.transcript.append(move, turn.narration, turn.state_change, turn.tool_calls, turn.recalled)
        return turn

    def ask(self, question: str) -> str:
        """An out-of-character question, answered from memory. Nothing is saved to the campaign."""
        cfg = self.config["narration"]
        move = ("(Out of character. The player asks the game master a question about the campaign so far. "
                "Answer in one or two sentences from what you know. If you don't know, say so.)\n"
                f"Question: {question}")
        messages, _ = self._prompt(move)
        search_only = [t for t in gm.TOOLS if t.name == "search_memory"] if cfg["tools"] else None
        reply = self.llm.complete(self.system, messages, cfg["max_output_tokens"], purpose="quiz",
                                  tools=search_only, tool_handler=self.run_tool, schema=gm.ANSWER_SCHEMA,
                                  max_tool_rounds=cfg["max_tool_rounds"])
        self.last_reply = reply
        try:
            return str(json.loads(reply.text).get("answer", ""))
        except (json.JSONDecodeError, AttributeError):
            return reply.text


def _is_long_flag(value) -> bool:
    return isinstance(value, str) and len(value) > MAX_FLAG_CHARS


def _flag_topic(name: str) -> str:
    return name.replace("_", " ").strip()


def format_state(state: dict) -> str:
    hero = state.get("hero", {})
    lines = [
        f"{hero.get('name', 'Hero')}  HP {hero.get('hp')}/{hero.get('max_hp')}  "
        f"Purse {format_money(state.get('copper', 0))}",
        f"At: {state.get('location', '?')}",
        f"Carrying: {', '.join(state.get('inventory', [])) or 'nothing'}",
    ]
    for place, items in state.get("stored", {}).items():
        lines.append(f"Left at {place}: {', '.join(items)}")
    if state.get("flags"):
        lines.append("Flags: " + ", ".join(f"{k}={json.dumps(v)}" for k, v in state["flags"].items()))
    return "\n".join(lines)


def format_turn_tokens(reply: Reply | None) -> str:
    if reply is None:
        return ""
    calls = f", {reply.calls} calls" if reply.calls > 1 else ""
    return f"[{reply.input_tokens:,} in ({reply.cached_tokens:,} cached) / {reply.output_tokens:,} out{calls}]"


def format_tool_calls(calls: list[dict], recalled: list[str] | None = None) -> list[str]:
    lines = [f"  recalled: {', '.join(recalled)}"] if recalled else []
    for call in calls:
        if call["name"] == "remember":
            lines.append(f"  remembered: {call['args'].get('fact', '')}")
        elif call["name"] == "search_memory":
            lines.append(f"  searched memory for: {call['args'].get('query', '')}")
    return lines


def format_usage(usage: UsageLog) -> str:
    from datetime import datetime, timezone

    today = usage.totals(datetime.now(timezone.utc).date().isoformat())
    total = usage.totals()
    return (
        f"Today: {today['calls']} calls, {today['input']:,} in / {today['output']:,} out "
        f"({today['cached']:,} cached)\n"
        f"All time: {total['calls']} calls, {total['input']:,} in / {total['output']:,} out"
    )


def run_dream(game: Game, config: dict, force: bool) -> None:
    from .dream import DreamError, dream, format_dream, make_dream_llm

    try:
        llm = make_dream_llm(config, game.campaign.usage)
        print("Dreaming...")
        result = dream(game.campaign, llm, gm.load_rules(ROOT / "prompts", "dream.md"), config, force=force)
    except (DreamError, BudgetExceeded) as e:
        print(e)
        return
    except Exception as e:  # usually a missing API key for the dream provider
        print(f"Could not dream: {e}")
        return
    if result is None:
        print("Nothing new to dream about yet.")
        return
    game.reload_canon()
    print(format_dream(result))


def format_page(page) -> str:
    lines = [f"{page.name} ({page.kind}): {page.summary}"]
    if page.aliases:
        lines.append(f"Also called: {', '.join(page.aliases)}")
    lines += [f"- {f.text} [{f.turn}]" for f in page.facts]
    lines += [f"! {c}" for c in page.contradictions]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from .dream import load_dream_state, undreamed_turns

    parser = argparse.ArgumentParser(description="Play Lorekeeper.")
    parser.add_argument("--campaign", default="default", help="campaign name (a folder under campaigns/)")
    parser.add_argument("--provider", choices=["gemini", "claude"], help="override the narration provider")
    parser.add_argument("--config", type=Path, default=ROOT / "config.toml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    campaign = Campaign(ROOT / "campaigns" / args.campaign)
    try:
        provider = make_provider(config, args.provider)
    except Exception as e:  # usually a missing API key
        print(f"Could not start the {args.provider or config['narration']['provider']} model: {e}")
        print("Set GEMINI_API_KEY (Gemini) or ANTHROPIC_API_KEY (Claude) and try again.")
        return 1
    llm = Budgeted(provider, campaign.usage, config["budget"]["daily_token_cap"])
    game = Game(campaign, llm, gm.load_rules(ROOT / "prompts"), config)

    print(f"Lorekeeper. Campaign '{args.campaign}', session {game.transcript.session}.")
    print("Commands: /state  /notes  /wiki [name]  /search <words>  /dream  /usage  /quit\n")
    recap = load_dream_state(campaign).get("recap")
    if recap:
        print(f"Previously: {recap}\n")
    print(format_state(game.state), "\n")

    while True:
        try:
            move = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not move:
            continue
        if move == "/quit":
            break
        if move == "/state":
            print(format_state(game.state), "\n")
            continue
        if move == "/notes":
            notes = campaign.notes.all()
            print("\n".join(format_note(n) for n in notes) if notes else "No notes yet.", "\n")
            continue
        if move.startswith("/wiki"):
            name = move[len("/wiki"):].strip()
            if name:
                page = campaign.wiki.find(name)
                print(format_page(page) if page else f"No page for {name!r}.", "\n")
            else:
                pages = campaign.wiki.all()
                print("\n".join(p.cast_line() for p in pages) if pages else "No wiki pages yet. They appear after /dream.", "\n")
            continue
        if move.startswith("/search"):
            query = move[len("/search"):].strip()
            print(format_hits(search(campaign.transcripts, campaign.notes, query, wiki=campaign.wiki))
                  if query else "Usage: /search <words>", "\n")
            continue
        if move == "/dream":
            run_dream(game, config, force=True)
            print()
            continue
        if move == "/usage":
            print(format_usage(campaign.usage), "\n")
            continue
        try:
            turn = game.take_turn(move)
        except BudgetExceeded as e:
            print(e)
            break
        print(f"\n{turn.narration}\n")
        for line in format_tool_calls(turn.tool_calls, turn.recalled):
            print(line)
        notes = [format_turn_tokens(game.last_reply)]
        if turn.parse_error:
            notes.append(f"state not updated: {turn.parse_error}")
        print("  ".join(notes), "\n")

    if config["dream"]["on_quit"] and len(undreamed_turns(campaign)) >= config["dream"]["min_turns"]:
        run_dream(game, config, force=False)
    print(format_usage(campaign.usage))
    print(f"Saved. This session's transcript: {game.transcript.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
