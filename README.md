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
The game master ends every reply with a small `state` block that the game uses
to update money, location and items. If it ever forgets, you'll see
`state not updated: no state block` after that turn.
Use `--campaign <name>` to keep more than one campaign.

## Where things live

Each campaign is a folder under `campaigns/` (ignored by git):

| File | What it is |
| --- | --- |
| `canon.md` | Injected context: loaded into every turn. Starts from a fantasy template. |
| `state.json` | Hit points, money (in copper), location, carried and stored items, flags. Updated by code only. |
| `transcripts/s001.jsonl` | One line per turn, with ids like `s001-t0004`. |
| `usage.jsonl` | Token counts for every model call. |

## Keeping costs down

- Narration runs on Gemini Flash with a low thinking level by default.
- Each prompt holds the rules, canon, recent turns and the current state, with
  the parts that don't change placed first so caching can reuse them.
- The recent-turns window moves forward 10 turns at a time instead of one, so
  the start of the prompt stays the same between jumps and stays cached. With
  Claude, the replayed history is marked for caching too.
- Each turn prints its own token count, like `[8,812 in (6,400 cached) / 512 out]`.
- `budget.daily_token_cap` in `config.toml` stops play once the day's tokens
  run out. `/usage` shows where you are.

## Tests

```bash
python -m pytest
```

The tests use a fake model, so they cost nothing.
