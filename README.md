# Lorekeeper

A fantasy text adventure whose game master remembers your campaign. It's an
experiment in the layered agent memory and offline "dreaming" described in
Anthropic's [components of agent memory](https://www.anthropic.com/research/components-of-agent-memory)
article.

This is **milestone 1: a playable loop**. The game master narrates, code tracks
the hero's state, every turn is saved to a transcript, and every model call is
logged with its token counts. Notes, dreaming and the wiki come in later
milestones.

## Run it

```bash
pip install -e ".[dev]"
export GEMINI_API_KEY=...        # default narrator: gemini-3.8-flash
python -m lorekeeper.play
```

To narrate with Claude Haiku 5.5 instead:

```bash
export ANTHROPIC_API_KEY=...
python -m lorekeeper.play --provider claude
```

In the game, type what your hero does. Commands: `/state`, `/usage`, `/quit`.
Use `--campaign <name>` to keep more than one campaign.

## Where things live

Each campaign is a folder under `campaigns/` (ignored by git):

| File | What it is |
| --- | --- |
| `canon.md` | Injected context: loaded into every turn. Starts from a fantasy template. |
| `state.json` | Hit points, gold, location, inventory, flags. Updated by code only. |
| `transcripts/s001.jsonl` | One line per turn, with ids like `s001-t0004`. |
| `usage.jsonl` | Token counts for every model call. |

## Keeping costs down

- Narration runs on Gemini Flash with a low thinking level by default.
- Each prompt holds the rules, canon, the last 20 turns and the current state,
  with the parts that don't change placed first so caching can reuse them.
- `budget.daily_token_cap` in `config.toml` stops play once the day's tokens
  run out. `/usage` shows where you are.

## Tests

```bash
python -m pytest
```

The tests use a fake model, so they cost nothing.
