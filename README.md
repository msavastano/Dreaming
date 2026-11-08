# Lorekeeper

A fantasy text adventure whose game master remembers your campaign. It's an
experiment in the layered agent memory and offline "dreaming" described in
Anthropic's [components of agent memory](https://www.anthropic.com/research/components-of-agent-memory)
article.

This is **milestone 2: notes and search**. The game master narrates, code tracks
the hero's state, every turn is saved to a transcript, and every model call is
logged with its token counts. The game master can now save facts as notes and
search the whole campaign for anything that has scrolled out of its recent
turns. Dreaming and the wiki come in later milestones.

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

In the game, type what your hero does. Commands:

| Command | What it does |
| --- | --- |
| `/state` | Hit points, purse, location, carried and stored items, flags |
| `/notes` | Every fact the game master has saved |
| `/search <words>` | Search notes and every past turn, the same way the game master does |
| `/usage` | Token counts for today and all time |
| `/quit` | Save and leave |

The game master replies in JSON with two parts: the narration and the state
change. Both models are asked for a fixed JSON format, so the state change
can't be left out. If a reply is cut off, you'll still see the narration, with
`state not updated: …` after it.

### Memory

The game master has two tools:

- `remember` saves a lasting fact, such as a name, a promise or a description,
  as a note that cites the turn it came from. You'll see `remembered: …` under
  that turn.
- `search_memory` searches notes and every past turn. You'll see
  `searched memory for: …`.

The latest notes (40 by default, `narration.notes_in_prompt`) go into every
prompt, so the game master sees them without searching. A turn that uses a
tool makes an extra model call, shown as `2 calls` in the token line. Each turn
allows at most 3 tool rounds (`narration.max_tool_rounds`).

Flags in the state are short switches like `room_rented`. If the game master
writes a flag longer than 60 characters, the game saves it as a note instead,
because the state goes into every prompt uncached. Older campaigns with long
flags have them moved to notes the next time they load.

Search ranks the exact phrase first, then turns with every word, then turns
with any word.
Use `--campaign <name>` to keep more than one campaign.

## Where things live

Each campaign is a folder under `campaigns/` (ignored by git):

| File | What it is |
| --- | --- |
| `canon.md` | Injected context: loaded into every turn. Starts from a fantasy template. |
| `state.json` | Hit points, money (in copper), location, carried and stored items, flags. Updated by code only. |
| `transcripts/s001.jsonl` | One line per turn, with ids like `s001-t0004`. Tool calls are kept under `tools`. |
| `notes/n0001.md` | One saved fact per file. Each one is `unverified` until dreaming checks it in milestone 3. |
| `usage.jsonl` | Token counts for every model call. |

## Keeping costs down

- Narration runs on Gemini Flash with a low thinking level by default.
- Each prompt holds the rules, canon, recent turns and the current state, with
  the parts that don't change placed first so caching can reuse them.
- The recent-turns window moves forward 10 turns at a time instead of one, so
  the start of the prompt stays the same between jumps and stays cached. With
  Claude, the replayed history is marked for caching too.
- Each turn prints its own token count, like `[8,812 in (6,400 cached) / 512 out]`.
- Search runs locally with SQLite full-text search, so it costs no tokens. Only
  the results the game master asks for go back into the prompt.
- `budget.daily_token_cap` in `config.toml` stops play once the day's tokens
  run out. `/usage` shows where you are.

## Tests

```bash
python -m pytest
```

The tests use a fake model, so they cost nothing.
