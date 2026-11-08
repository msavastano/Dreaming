"""Measure whether memory helps: replay one scripted campaign under three setups and quiz each.

    python -m lorekeeper.eval --provider claude              # all three setups
    python -m lorekeeper.eval --setups A,C --turns 30        # a cheaper partial run

Setups (from the plan):
  A  No notes: the recent-turns window and the state sheet (flags, people, inventory) only.
     No tools, notes or recall. The state sheet is itself a small memory, so the report also
     counts the questions whose answer wasn't on it.
  B  Notes: A plus remember, search_memory, notes in the prompt and recall.
  C  Notes + dreaming: B plus a dream every `dream_every` turns (wiki pages, checked notes, cast in canon).

The player's moves are fixed, and the facts the quiz asks about are said by the player, so
every setup can be graded against the same answer key. The game master's replies differ
between setups. A wrong note is planted early in B and C to see whether dreaming catches it.

Each run writes its campaigns under evals/runs/ and a report under evals/results/.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import gm
from .config import load_config
from .dream import DreamError, dream, make_dream_llm
from .llm import Budgeted, make_provider
from .play import ROOT, Campaign, Game
from .transcript import load_all_turns, load_window

SETUPS = {
    "A": "Window + state sheet, no notes",
    "B": "Notes (remember, search, recall)",
    "C": "Notes + dreaming",
}
# Rough Haiku 5.5 prices per million tokens, ignoring the cache discount, so the estimate is an upper bound.
HAIKU_PRICE = {"input": 0.10, "output": 0.50}


def grade(answer: str, needs: list[list[str]]) -> bool:
    """Correct when every group has at least one of its words in the answer."""
    text = re.sub(r"\s+", " ", answer.lower())
    return all(any(word.lower() in text for word in group) for group in needs)


@dataclass
class SetupResult:
    setup: str
    answers: list[dict] = field(default_factory=list)  # {checkpoint, id, question, answer, correct, in_view}
    usage: dict = field(default_factory=dict)          # purpose -> {calls, input, output, cached}
    turns: int = 0
    parse_errors: int = 0
    remember_calls: int = 0
    search_calls: int = 0
    recall_turns: int = 0
    notes: int = 0
    wrong_note_status: str = ""
    wiki_pages: int = 0
    wiki_chars: int = 0
    transcript_chars: int = 0
    stopped: str = ""
    dream_failures: list[str] = field(default_factory=list)

    def accuracy(self, in_view: bool | None = None, checkpoint: int | None = None,
                 in_state: bool | None = None) -> tuple[int, int]:
        rows = [a for a in self.answers if (in_view is None or a["in_view"] == in_view)
                and (checkpoint is None or a["checkpoint"] == checkpoint)
                and (in_state is None or a.get("in_state", False) == in_state)]
        return sum(a["correct"] for a in rows), len(rows)


def setup_config(base: dict, setup: str, cap: int) -> dict:
    config = copy.deepcopy(base)
    config["budget"]["daily_token_cap"] = cap
    config["dream"]["on_quit"] = False
    if setup == "A":
        config["narration"].update(tools=False, notes_in_prompt=0, recall_hits=0)
    return config


def run_setup(setup: str, script: dict, folder: Path, base_config: dict, provider, dream_llm_factory,
              turns: int, cap: int, log=print) -> SetupResult:
    config = setup_config(base_config, setup, cap)
    campaign = Campaign(folder)
    game = Game(campaign, Budgeted(provider, campaign.usage, cap), gm.load_rules(ROOT / "prompts"), config)
    dream_rules = gm.load_rules(ROOT / "prompts", "dream.md")
    dream_llm = dream_llm_factory(config, campaign.usage) if setup == "C" else None
    result = SetupResult(setup)
    wrong = script.get("wrong_note")
    quiz_after = [q for q in script["quiz_after"] if q <= turns] or [turns]
    try:
        for i, move in enumerate(script["moves"][:turns], start=1):
            turn = game.take_turn(move)
            result.turns = i
            if turn.parse_error:
                result.parse_errors += 1
            if wrong and setup in ("B", "C") and i == wrong["after"]:
                campaign.notes.add(wrong["text"], wrong["about"], turn=f"s001-t{i:04d}")
            if setup == "C" and i % script["dream_every"] == 0:
                try:
                    done = dream(campaign, dream_llm, dream_rules, config, force=True)
                    game.reload_canon()
                    split = f", split {done.splits} chunk(s)" if done and done.splits else ""
                    log(f"  [{setup}] dreamed at turn {i}{split}")
                except DreamError as e:  # keep playing; the next dream retries these turns
                    result.dream_failures.append(f"turn {i}: {e}")
                    log(f"  [{setup}] dream failed at turn {i}: {e}")
            if i in quiz_after:
                window = {t["id"] for t in load_window(campaign.transcripts, config["narration"]["window_turns"],
                                                       config["narration"]["window_step"])}
                for item in script["key"]:
                    if item["planted"] > i:
                        continue
                    answer = game.ask(item["q"])
                    planted = f"s001-t{item['planted']:04d}"
                    state_text = json.dumps(game.state, ensure_ascii=False)
                    result.answers.append({
                        "checkpoint": i, "id": item["id"], "question": item["q"], "answer": answer,
                        "correct": grade(answer, item["needs"]),
                        # Canon facts (planted 0) are always in view.
                        "in_view": item["planted"] == 0 or planted in window,
                        # The state sheet is in every prompt, so a fact on it isn't a test of notes or dreaming.
                        "in_state": grade(state_text, item["needs"]),
                    })
                right, total = result.accuracy(checkpoint=i)
                log(f"  [{setup}] quiz after turn {i}: {right}/{total}")
            elif i % 10 == 0:
                log(f"  [{setup}] turn {i}")
    except Exception as e:  # a budget stop or an API error ends this setup but keeps the others
        result.stopped = f"{type(e).__name__}: {e}"
        log(f"  [{setup}] stopped at turn {result.turns}: {result.stopped}")

    for rec in (json.loads(l) for l in campaign.usage.path.read_text().splitlines()) if campaign.usage.path.exists() else []:
        u = result.usage.setdefault(rec.get("purpose", "?"), {"calls": 0, "input": 0, "output": 0, "cached": 0})
        u["calls"] += 1
        u["input"] += rec.get("input", 0)
        u["output"] += rec.get("output", 0)
        u["cached"] += rec.get("cached", 0)
    all_turns = load_all_turns(campaign.transcripts)
    for t in all_turns:
        names = [c["name"] for c in t.get("tools", []) if not c.get("from_flag")]
        result.remember_calls += names.count("remember")
        result.search_calls += names.count("search_memory")
        result.recall_turns += bool(t.get("recalled"))
    notes = campaign.notes.all()
    result.notes = len(notes)
    if wrong and setup in ("B", "C"):
        result.wrong_note_status = next((n.status for n in notes if n.text == " ".join(wrong["text"].split())), "")
    pages = list((folder / "wiki").glob("*.md")) if (folder / "wiki").exists() else []
    result.wiki_pages = len(pages)
    result.wiki_chars = sum(len(p.read_text()) for p in pages)
    result.transcript_chars = sum(len(t["player"]) + len(t["narration"]) for t in all_turns)
    return result


def _pct(right: int, total: int) -> str:
    return f"{right}/{total} ({100 * right // total}%)" if total else "-"


def report(results: list[SetupResult], script: dict, meta: dict) -> str:
    lines = [f"# Memory eval: {script['name']}", "",
             f"{meta['when']} · narration: {meta['provider']} · dreaming: {meta['dream_provider']} · "
             f"{meta['turns']} turns", "",
             "Out of view means the fact's turn had left the game master's recent-turns window, so only memory "
             "could supply it. The state sheet (flags, people, inventory) is in every prompt, so \"out of view, "
             "not on the sheet\" is the column that measures notes and dreaming.", "",
             "| Setup | Out of view, not on the sheet | Quiz, out of view | Quiz, all | Notes "
             "| remember / search calls | Turns with recall | Tokens per turn (in / cached / out) | Dream tokens "
             "| Wiki pages |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        play = r.usage.get("narrate", {"calls": 0, "input": 0, "output": 0, "cached": 0})
        per = max(r.turns, 1)
        d = r.usage.get("dream")
        dream_tokens = f"{d['input']:,} / {d['output']:,}" if d else "-"
        lines.append(
            f"| {r.setup}. {SETUPS[r.setup]} | {_pct(*r.accuracy(in_view=False, in_state=False))} "
            f"| {_pct(*r.accuracy(in_view=False))} | {_pct(*r.accuracy())} "
            f"| {r.notes} | {r.remember_calls} / {r.search_calls} | {r.recall_turns} "
            f"| {play['input'] // per:,} / {play['cached'] // per:,} / {play['output'] // per:,} "
            f"| {dream_tokens} | {r.wiki_pages} |")
    lines += ["", "## Per question", ""]
    checkpoints = sorted({a["checkpoint"] for r in results for a in r.answers})
    header = "| Question | " + " | ".join(f"{r.setup} @{c}" for c in checkpoints for r in results) + " |"
    lines += [header, "|" + " --- |" * (1 + len(checkpoints) * len(results))]
    for item in script["key"]:
        cells = []
        for c in checkpoints:
            for r in results:
                a = next((a for a in r.answers if a["id"] == item["id"] and a["checkpoint"] == c), None)
                cells.append("-" if a is None else ("yes" if a["correct"] else "no") + ("" if a["in_view"] else "*")
                             + ("s" if a.get("in_state") else ""))
        lines.append(f"| {item['q']} | " + " | ".join(cells) + " |")
    lines += ["", "\\* out of view when asked. s: the answer was on the state sheet.", ""]
    extra = []
    for r in results:
        if r.wrong_note_status:
            extra.append(f"- {r.setup}: the planted wrong note ended as **{r.wrong_note_status}**.")
        if r.wiki_chars:
            extra.append(f"- {r.setup}: wiki is {r.wiki_chars / max(r.transcript_chars, 1):.2f}x the transcript's size.")
        if r.parse_errors:
            extra.append(f"- {r.setup}: {r.parse_errors} turns had no usable state change.")
        for f in r.dream_failures:
            extra.append(f"- {r.setup}: dream failed at {f}")
        if r.stopped:
            extra.append(f"- {r.setup}: stopped early at turn {r.turns}: {r.stopped}")
    if extra:
        lines += ["## Notes", ""] + extra + [""]
    return "\n".join(lines)


def estimate(turns: int, setups: list[str], quizzes: int) -> tuple[int, int]:
    calls = len(setups) * (turns + quizzes)
    return calls * 9_000, calls * 600  # input, output; rough, from playtests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a scripted campaign under memory setups A, B and C.")
    parser.add_argument("--script", type=Path, default=ROOT / "evals" / "thornwick-60.json")
    parser.add_argument("--setups", default="A,B,C", help="comma-separated, from A, B, C")
    parser.add_argument("--turns", type=int, help="play only the first N moves (default: the whole script)")
    parser.add_argument("--provider", choices=["gemini", "claude"], help="narration provider (default: config)")
    parser.add_argument("--dream-provider", choices=["gemini", "claude"], help="dream provider (default: config)")
    parser.add_argument("--max-tokens", type=int, default=2_000_000, help="token cap for each setup")
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    parser.add_argument("--config", type=Path, default=ROOT / "config.toml")
    args = parser.parse_args(argv)

    script = json.loads(args.script.read_text())
    setups = [s.strip().upper() for s in args.setups.split(",") if s.strip()]
    if any(s not in SETUPS for s in setups):
        parser.error(f"setups must come from {', '.join(SETUPS)}")
    turns = min(args.turns or len(script["moves"]), len(script["moves"]))
    config = load_config(args.config)
    provider_name = args.provider or config["narration"]["provider"]
    dream_name = args.dream_provider or config["dream"]["provider"]

    quizzes = sum(1 for q in script["quiz_after"] if q <= turns for item in script["key"] if item["planted"] <= q)
    est_in, est_out = estimate(turns, setups, quizzes)
    print(f"{len(setups)} setups x {turns} turns, {quizzes} quiz questions each, narrated by {provider_name}.")
    print(f"Rough size: {est_in:,} input and {est_out:,} output tokens in total, most input cached.")
    if provider_name == "claude":
        cost = est_in / 1e6 * HAIKU_PRICE["input"] + est_out / 1e6 * HAIKU_PRICE["output"]
        print(f"On Haiku 5.5 that's at most about ${cost:.2f} before the cache discount, plus dreaming.")
    if not args.yes and input("Run it? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Cancelled.")
        return 0

    try:
        provider = make_provider(config, provider_name)
    except Exception as e:
        print(f"Could not start the {provider_name} model: {e}")
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "evals" / "runs" / f"{stamp}-{script['name']}"
    results = []
    for setup in setups:
        print(f"Setup {setup}: {SETUPS[setup]}")
        results.append(run_setup(
            setup, script, run_dir / setup, config, provider,
            lambda cfg, usage: make_dream_llm(cfg, usage, dream_name), turns, args.max_tokens))

    meta = {"when": stamp, "provider": provider_name, "dream_provider": dream_name, "turns": turns}
    text = report(results, script, meta)
    out = ROOT / "evals" / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stamp}-{script['name']}-{provider_name}.md").write_text(text)
    (out / f"{stamp}-{script['name']}-{provider_name}.json").write_text(json.dumps(
        {"meta": meta, "results": [r.__dict__ for r in results]}, indent=2))
    print()
    print(text)
    print(f"Saved to {out} and campaigns to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
