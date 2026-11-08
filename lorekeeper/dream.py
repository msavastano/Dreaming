"""Dreaming: the offline pass that turns transcripts into wiki pages and canon.

    python -m lorekeeper.dream                     # dream the default campaign
    python -m lorekeeper.dream --campaign test2 --force

Play only appends to memory. Dreaming is the only step that rewrites it:
1. Collect the turns since the last dream.
2. One model call per chunk of turns returns updated wiki pages, a verdict on
   each unchecked note, the story so far and the open threads.
3. Code checks every fact against the turn it cites and drops the ones whose
   quote isn't there.
4. canon.md is rebuilt: story so far, open threads, and a one-line cast entry
   per wiki page. The old canon is kept as canon.prev.md and the diff is shown.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .checks import _norm, quote_found, turn_text
from .llm import Budgeted, Message, make_provider
from .transcript import load_all_turns
from .wiki import KINDS, Fact, Page

STRING_LIST = {"type": "array", "items": {"type": "string"}}
DREAM_SCHEMA = {
    "type": "object",
    "properties": {
        "pages": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "kind": {"type": "string", "enum": list(KINDS)},
                "aliases": STRING_LIST,
                "summary": {"type": "string"},
                "facts": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}, "turn": {"type": "string"}, "quote": {"type": "string"}},
                    "required": ["text", "turn", "quote"],
                    "additionalProperties": False,
                }},
                "contradictions": STRING_LIST,
            },
            "required": ["name", "kind", "aliases", "summary", "facts", "contradictions"],
            "additionalProperties": False,
        }},
        "notes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "verdict": {"type": "string", "enum": ["confirmed", "wrong", "unsupported"]},
                "correction": {"type": "string"},
            },
            "required": ["id", "verdict", "correction"],
            "additionalProperties": False,
        }},
        "story_so_far": {"type": "string"},
        "open_threads": STRING_LIST,
        "recap": {"type": "string"},
    },
    "required": ["pages", "notes", "story_so_far", "open_threads", "recap"],
    "additionalProperties": False,
}

OWNED_SECTIONS = ("Story so far", "Open threads", "Cast", "Contradictions to keep straight")


class DreamError(Exception):
    pass


@dataclass
class DreamResult:
    turns: int = 0
    new_pages: list[str] = field(default_factory=list)
    updated_pages: list[str] = field(default_factory=list)
    notes: dict[str, int] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)  # facts thrown away by the quote check
    recap: str = ""
    canon_diff: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


# --- dream state -------------------------------------------------------------

def _state_path(campaign) -> Path:
    return campaign.folder / "dream_state.json"


def load_dream_state(campaign) -> dict:
    path = _state_path(campaign)
    return json.loads(path.read_text()) if path.exists() else {"dreamed_turns": 0, "recap": ""}


def undreamed_turns(campaign) -> list[dict]:
    return load_all_turns(campaign.transcripts)[load_dream_state(campaign)["dreamed_turns"]:]


# --- canon sections ----------------------------------------------------------

def split_canon(text: str) -> tuple[str, list[tuple[str, str]]]:
    preamble, sections, title, body = [], [], None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if title is not None:
                sections.append((title, "\n".join(body).strip()))
            title, body = line[3:].strip(), []
        elif title is None:
            preamble.append(line)
        else:
            body.append(line)
    if title is not None:
        sections.append((title, "\n".join(body).strip()))
    return "\n".join(preamble).strip(), sections


def join_canon(preamble: str, sections: list[tuple[str, str]]) -> str:
    parts = [preamble] if preamble else []
    parts += [f"## {title}\n{body}".rstrip() for title, body in sections]
    return "\n\n".join(parts) + "\n"


def _set_section(sections: list[tuple[str, str]], title: str, body: str) -> None:
    for i, (t, _) in enumerate(sections):
        if t.lower() == title.lower():
            sections[i] = (t, body)
            return
    sections.append((title, body))


def _get_section(sections: list[tuple[str, str]], title: str) -> str:
    return next((b for t, b in sections if t.lower() == title.lower()), "")


# --- the dream -----------------------------------------------------------------

def dream(campaign, llm: Budgeted, rules: str, config: dict, force: bool = False) -> DreamResult | None:
    """Dream over every undreamed turn. Returns None if there is too little to dream about."""
    cfg = config["dream"]
    turns = undreamed_turns(campaign)
    if not turns or (len(turns) < cfg["min_turns"] and not force):
        return None
    all_turns = {t["id"]: t for t in load_all_turns(campaign.transcripts)}
    canon_before = campaign.canon_path.read_text()
    preamble, sections = split_canon(canon_before)
    result = DreamResult(turns=len(turns))
    state = load_dream_state(campaign)

    unchecked = [n for n in campaign.notes.all() if n.status == "unverified"]
    size = cfg["chunk_turns"]
    chunks = [turns[i:i + size] for i in range(0, len(turns), size)]
    # A note goes with the chunk holding its turn. Notes from older turns or from flags go with the last chunk.
    chunk_of = {t["id"]: c for c, ch in enumerate(chunks) for t in ch}
    for c, chunk in enumerate(chunks):
        notes = [n for n in unchecked if chunk_of.get(n.turn, len(chunks) - 1) == c]
        reply, given = _dream_chunk(campaign, llm, rules, cfg, chunk, notes, sections)
        result.calls += reply.calls
        result.input_tokens += reply.input_tokens
        result.output_tokens += reply.output_tokens
        if reply.stop_reason == "max_tokens":
            raise DreamError(
                f"The dream ran out of output room ({reply.output_tokens:,} tokens, most of it the model's "
                f"thinking) before it finished. Nothing was changed for these turns. Raise dream.max_output_tokens "
                f"(now {cfg['max_output_tokens']:,}) or lower dream.chunk_turns (now {cfg['chunk_turns']}).")
        try:
            data = json.loads(reply.text)
        except json.JSONDecodeError as e:
            raise DreamError(f"The dream reply was not valid JSON ({e}; stop reason {reply.stop_reason or 'unknown'}, "
                             f"{reply.output_tokens:,} output tokens). Nothing was changed for these turns.") from e
        _apply(campaign, data, chunk, all_turns, sections, result, given)
        # Save progress after each chunk, so a failure later doesn't redo this one.
        state["dreamed_turns"] += len(chunk)
        state["recap"] = " ".join(data.get("recap", "").split())
        _write_canon(campaign, preamble, sections, cfg)
        state["last_dream"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _state_path(campaign).write_text(json.dumps(state, indent=2))

    result.recap = state["recap"]
    canon_after = campaign.canon_path.read_text()
    (campaign.folder / "canon.prev.md").write_text(canon_before)
    result.canon_diff = "".join(difflib.unified_diff(
        canon_before.splitlines(True), canon_after.splitlines(True), "canon.prev.md", "canon.md", n=0))
    return result


def _dream_chunk(campaign, llm, rules, cfg, chunk, notes, sections):
    text = "\n".join(turn_text(t) for t in chunk)
    pages = campaign.wiki.all()
    given = [p for p in pages if p.mentioned_in(text) or any(p.mentioned_in(n.text) for n in notes)]
    others = [p for p in pages if p not in given]
    parts = [
        f"<story_so_far>\n{_get_section(sections, 'Story so far')}\n</story_so_far>",
        f"<open_threads>\n{_get_section(sections, 'Open threads')}\n</open_threads>",
        "<wiki>\n" + "\n\n".join(p.render() for p in given) + "\n</wiki>",
        "<other_pages>\n" + "\n".join(p.cast_line() for p in others) + "\n</other_pages>",
        "<notes>\n" + "\n".join(f"[{n.id}, from {n.turn}] {n.text}" for n in notes) + "\n</notes>",
        "<turns>\n" + "\n\n".join(f"[{t['id']}]\nPlayer: {t['player']}\nGM: {t['narration']}" for t in chunk) + "\n</turns>",
    ]
    reply = llm.complete(rules, [Message("user", "\n\n".join(parts))], cfg["max_output_tokens"],
                         purpose="dream", schema=DREAM_SCHEMA)
    return reply, {p.slug for p in given}


def _apply(campaign, data: dict, chunk: list[dict], all_turns: dict, sections, result: DreamResult,
           sent: set[str]) -> None:
    last_id = chunk[-1]["id"]
    for entry in data.get("pages", []):
        name = " ".join(str(entry.get("name", "")).split())
        if not name:
            continue
        facts = []
        for f in entry.get("facts", []):
            turn = all_turns.get(f.get("turn", ""))
            if turn and quote_found(f.get("quote", ""), turn_text(turn)):
                facts.append(Fact(" ".join(f["text"].split()), f["turn"], " ".join(f["quote"].split())))
            else:
                result.dropped.append(f"{name}: {f.get('text', '')}")
        existing = campaign.wiki.find(name) or next(
            (p for a in entry.get("aliases", []) if (p := campaign.wiki.find(a))), None)
        if existing and existing.slug not in sent:
            # The model didn't see this page, so keep its old facts.
            seen = {_norm(f.text) for f in facts}
            facts = [f for f in existing.facts if _norm(f.text) not in seen] + facts
        if not facts and not existing:
            continue  # nothing checkable to say about it
        page = Page(
            name=name,
            kind=entry.get("kind") if entry.get("kind") in KINDS else "thing",
            summary=" ".join(entry.get("summary", "").split())[:200],
            aliases=[a for a in dict.fromkeys(" ".join(a.split()) for a in entry.get("aliases", [])) if a and a != name],
            facts=facts or existing.facts,
            contradictions=[" ".join(c.split()) for c in entry.get("contradictions", []) if c.strip()],
            updated=last_id,
        )
        campaign.wiki.save(page, old_slug=existing.slug if existing else None)
        (result.updated_pages if existing else result.new_pages).append(name)

    known = {n.id for n in campaign.notes.all()}
    for verdict in data.get("notes", []):
        if verdict.get("id") in known and verdict.get("verdict") in ("confirmed", "wrong", "unsupported"):
            campaign.notes.set_status(verdict["id"], verdict["verdict"], verdict.get("correction", ""))
            result.notes[verdict["verdict"]] = result.notes.get(verdict["verdict"], 0) + 1

    if data.get("story_so_far", "").strip():
        _set_section(sections, "Story so far", data["story_so_far"].strip())
    threads = [t.strip() for t in data.get("open_threads", []) if t.strip()][:8]
    if threads or data.get("open_threads") == []:
        _set_section(sections, "Open threads", "\n".join(f"- {t}" for t in threads) or "- None right now.")


def _write_canon(campaign, preamble: str, sections, cfg) -> None:
    pages = sorted(campaign.wiki.all(), key=lambda p: p.updated, reverse=True)[:cfg["cast_limit"]]
    cast = sorted(pages, key=lambda p: (KINDS.index(p.kind) if p.kind in KINDS else 9, p.name.lower()))
    if cast:
        _set_section(sections, "Cast", "Everyone and everything met so far. Keep them consistent with this.\n"
                     + "\n".join(p.cast_line() for p in cast))
    contradictions = [f"- {p.name}: {c}" for p in pages for c in p.contradictions][:10]
    if contradictions:
        _set_section(sections, "Contradictions to keep straight", "\n".join(contradictions))
    campaign.canon_path.write_text(join_canon(preamble, sections))


# --- running it ----------------------------------------------------------------

def make_dream_llm(config: dict, usage, override: str | None = None) -> Budgeted:
    cfg = copy.deepcopy(config)
    cfg["claude"]["effort"] = config["dream"]["effort"]
    cfg["gemini"]["thinking_level"] = config["dream"]["thinking_level"]
    provider = make_provider(cfg, override or config["dream"]["provider"])
    return Budgeted(provider, usage, config["budget"]["daily_token_cap"])


def format_dream(result: DreamResult) -> str:
    lines = [f"Dreamed over {result.turns} turns  "
             f"[{result.input_tokens:,} in / {result.output_tokens:,} out, {result.calls} call{'s' * (result.calls > 1)}]"]
    if result.new_pages:
        lines.append(f"New pages: {', '.join(result.new_pages)}")
    if result.updated_pages:
        lines.append(f"Updated pages: {', '.join(result.updated_pages)}")
    if result.notes:
        lines.append("Notes: " + ", ".join(f"{v} {k}" for k, v in sorted(result.notes.items())))
    if result.dropped:
        lines.append(f"Dropped {len(result.dropped)} fact(s) whose quote wasn't in the turn:")
        lines += [f"  {d}" for d in result.dropped]
    if result.canon_diff:
        lines += ["", "Canon changes:", result.canon_diff.rstrip()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from .config import load_config
    from .play import ROOT, Campaign

    parser = argparse.ArgumentParser(description="Dream over a Lorekeeper campaign's new turns.")
    parser.add_argument("--campaign", default="default")
    parser.add_argument("--provider", choices=["gemini", "claude"], help="override dream.provider")
    parser.add_argument("--force", action="store_true", help=f"dream even with fewer than dream.min_turns new turns")
    parser.add_argument("--config", type=Path, default=ROOT / "config.toml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    campaign = Campaign(ROOT / "campaigns" / args.campaign)
    try:
        llm = make_dream_llm(config, campaign.usage, args.provider)
    except Exception as e:
        print(f"Could not start the dream model: {e}")
        return 1
    try:
        result = dream(campaign, llm, (ROOT / "prompts" / "dream.md").read_text(), config, force=args.force)
    except DreamError as e:
        print(e)
        return 1
    if result is None:
        print(f"Only {len(undreamed_turns(campaign))} new turns. Use --force to dream anyway.")
        return 0
    print(format_dream(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
