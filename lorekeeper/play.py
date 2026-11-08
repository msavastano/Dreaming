"""Play Lorekeeper in the terminal.

    python -m lorekeeper.play                    # default campaign, Gemini
    python -m lorekeeper.play --campaign quest2  # a second campaign
    python -m lorekeeper.play --provider claude  # narrate with Haiku instead

In-game commands: /state, /usage, /quit
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import gm
from .config import load_config
from .llm import Budgeted, BudgetExceeded, UsageLog, make_provider
from .state import apply_changes, load_state, save_state
from .transcript import Transcript, load_recent_turns

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"


class Campaign:
    """A campaign is one folder: canon.md, state.json, transcripts/, usage.jsonl."""

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


class Game:
    def __init__(self, campaign: Campaign, llm: Budgeted, rules: str, config: dict):
        self.campaign = campaign
        self.llm = llm
        self.config = config
        self.state = load_state(campaign.state_path)
        self.system = gm.build_system(rules, campaign.canon_path.read_text())
        self.transcript = Transcript(campaign.transcripts)

    def take_turn(self, move: str) -> gm.Turn:
        window = self.config["narration"]["window_turns"]
        recent = load_recent_turns(self.campaign.transcripts, window)
        messages = gm.build_messages(recent, self.state, move)
        reply = self.llm.complete(
            self.system, messages, self.config["narration"]["max_output_tokens"], purpose="narrate"
        )
        turn = gm.parse_reply(reply.text)
        if turn.state_change:
            self.state = apply_changes(self.state, turn.state_change)
            save_state(self.campaign.state_path, self.state)
        self.transcript.append(move, turn.narration, turn.state_change)
        return turn


def format_state(state: dict) -> str:
    hero = state.get("hero", {})
    items = ", ".join(state.get("inventory", [])) or "nothing"
    return (
        f"{hero.get('name', 'Hero')}  HP {hero.get('hp')}/{hero.get('max_hp')}  "
        f"Gold {state.get('gold', 0)}\nAt: {state.get('location', '?')}\nCarrying: {items}"
    )


def format_usage(usage: UsageLog) -> str:
    from datetime import datetime, timezone

    today = usage.totals(datetime.now(timezone.utc).date().isoformat())
    total = usage.totals()
    return (
        f"Today: {today['calls']} calls, {today['input']:,} in / {today['output']:,} out "
        f"({today['cached']:,} cached)\n"
        f"All time: {total['calls']} calls, {total['input']:,} in / {total['output']:,} out"
    )


def main(argv: list[str] | None = None) -> int:
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
    print("Commands: /state  /usage  /quit\n")
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
        if move == "/usage":
            print(format_usage(campaign.usage), "\n")
            continue
        try:
            turn = game.take_turn(move)
        except BudgetExceeded as e:
            print(e)
            break
        print(f"\n{turn.narration}\n")
        if turn.parse_error:
            print(f"(Note: the game master's state update was ignored: {turn.parse_error})\n", file=sys.stderr)

    print(format_usage(campaign.usage))
    print(f"Saved. This session's transcript: {game.transcript.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
