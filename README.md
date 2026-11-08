# Lorekeeper

A fantasy text adventure whose game master remembers your campaign. It's an
experiment in the layered agent memory and offline "dreaming" described in
Anthropic's [components of agent memory](https://www.anthropic.com/research/components-of-agent-memory)
article.

This is **milestone 4: measuring memory**. The game master narrates, code tracks the
hero's state, every turn is saved to a transcript, and every model call is
logged with its token counts. The game master can save notes and search the
whole campaign. After play, a dreaming pass reads the new turns and writes a
wiki page for every person, place and thing, checks the notes, and rebuilds
the canon that goes into every prompt. An eval replays a scripted campaign
with and without memory to show whether it helps.

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

### In your browser

```bash
python -m lorekeeper.web --provider claude     # opens http://127.0.0.1:8765
```

The same game, in a page: the story on the left and the hero's state sheet,
notes, wiki, canon and search on the right. Under each turn you can see what
memory did: turns recalled for it, facts the game master remembered, and
searches it ran. Turns that have left the game master's recent window are
faded. **Dream** folds new turns into the wiki and canon, and its badge
counts the turns not dreamed yet. Typing `/dream` or `/search <words>` in the
move box works too. Press Ctrl+C in the terminal to stop; like the terminal
game, it dreams on the way out once enough turns are new. The server only
listens on your own computer. Options: `--campaign`, `--port`, `--no-browser`.

### In the terminal

In the game, type what your hero does. Commands:

| Command | What it does |
| --- | --- |
| `/state` | Hit points, purse, location, carried and stored items, flags |
| `/notes` | Every fact the game master has saved |
| `/wiki [name]` | The cast list, or one wiki page with its facts and the turns they came from |
| `/search <words>` | Search notes, wiki pages and every past turn, the same way the game master does |
| `/dream` | Dream now, even after only a few turns |
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
prompt, so the game master sees them without searching.

The game also recalls on its own. Before each turn it searches notes and old
turns for the words in your move, locally and for free, and adds up to 3
matches to the prompt (`narration.recall_hits`). It only counts a match when at
least two of your words appear, and it skips turns the game master can already
see. You'll see `recalled: s001-t0002` under a turn when this happens. The
playtest showed why: asked about a song from turn 2, Haiku said there was no
record instead of searching. A turn that uses a
tool makes an extra model call, shown as `2 calls` in the token line. Each turn
allows at most 3 tool rounds (`narration.max_tool_rounds`).

Flags in the state are short switches like `room_rented`. If the game master
writes a flag longer than 60 characters, the game saves it as a note instead,
because the state goes into every prompt uncached. Older campaigns with long
flags have them moved to notes the next time they load.

Search ranks the exact phrase first, then turns with every word, then turns
with any word.
Use `--campaign <name>` to keep more than one campaign.

### Dreaming

When you `/quit` with at least 10 new turns (`dream.min_turns`), the game
dreams before it exits. You can also run `/dream` during play, or dream from
the shell:

```bash
python -m lorekeeper.dream --campaign test2          # add --force for short sessions
```

One model call per 25 new turns (`dream.chunk_turns`) returns:

- **Wiki pages** for each person, place, thing or group, including the hero.
  Every fact cites its turn and quotes a few words from it. Code checks each
  quote against the transcript and drops facts whose quote isn't there, so the
  dream can't invent them. Pages note where turns contradict each other.
- **A verdict on each note:** confirmed, wrong (with the correction) or
  unsupported. Only unchecked notes go into the play prompt after that,
  because the rest now live in the wiki.
- **The story so far, open threads and a recap.** The recap is shown as
  "Previously: …" when you next start.

Then `canon.md` is rebuilt with those sections, **The hero** (every checked
fact about the player's character), a **Cast** list with one line per wiki
page, and **Contradictions to keep straight**. Other sections, like
World rules, are kept as written. The old canon is saved as `canon.prev.md`
and the diff is printed. Canon sits in the system prompt, so it stays cached
between dreams.

Dreaming uses Haiku with low effort by default (`[dream]` in
`config.toml`). At medium effort Haiku's thinking used up all 16,000 output
tokens on 20 turns. If a dream call still runs out of room, it is retried as
two halves. Set `provider = "gemini"` to dream with Gemini Flash instead.

## Measuring whether memory helps

```bash
python -m lorekeeper.eval --provider claude          # asks before spending anything
python -m lorekeeper.eval --setups A,C --turns 30    # a cheaper partial run
```

The eval replays `evals/thornwick-60.json`, 60 fixed player moves, under three
setups:

| Setup | What the game master has |
| --- | --- |
| A. Window + state sheet | The recent-turns window and the state sheet (flags, people, inventory). No tools, notes or recall. |
| B. Notes | A, plus `remember`, `search_memory`, notes in the prompt and recall. |
| C. Notes + dreaming | B, plus a dream every 20 turns. |

The player states 12 facts in the first 24 turns: where Wren grew up, a debt to
Hobb, a promise to the smith, a secret told to Tam, and so on. After turns 30
and 60, each setup answers out-of-character quiz questions about them. Answers
are graded against a keyword answer key, so grading costs nothing. A wrong
note ("Wren's sister is a sailor named Mara") is planted in B and C to see
whether dreaming marks it wrong.

The report goes to `evals/results/` as Markdown and JSON. The column that
matters is **Out of view, not on the sheet**: questions about facts whose turn
had left the recent-turns window and that the game master hadn't written into
a state flag, so only notes or dreaming could answer them. The state sheet is
in every prompt, which is why setup A can still answer many out-of-view
questions. The report also
shows tokens per turn, dream tokens, tool use, the wrong note's final status
and the wiki's size compared with the transcript. Each setup's campaign is
kept under `evals/runs/` so you can read what happened. Before it runs, the
eval prints a rough token estimate and asks you to confirm; `--max-tokens`
caps each setup (2,000,000 by default).

### The harder script

```bash
python -m lorekeeper.eval --provider claude --script evals/thornwick-120.json
```

`evals/thornwick-120.json` is 120 moves and is built to be harder to game:

- **Questions avoid the planted turn's words.** "Why does Wren stay away from
  rivers and lakes?" shares nothing with "I'm afraid of deep water because my
  father drowned", so word-matching recall can't find the answer by itself.
- **Other people.** The player sets details about others, such as Tam being
  about twelve, Garra's burnt hand and Maren being blind, so every setup has
  the same answer key.
- **Facts that change.** The debt drops from three silver to two, Wren moves
  from the inn to Maren's loft, and the mule Pebble is sold for a pony named
  Ember. The quiz expects the latest version.
- **Two wrong notes.** "Wren grew up in Ashford" and "Tam is a grey-bearded
  fisherman in his forties". Some answers fail if they repeat a wrong note.
- **In-play probes.** Ten ordinary moves late in the game, like "I ask Tam how
  old he is" or "I saddle my mount", are graded on the narration itself. They
  check that the game master uses what it knows during play, not only when
  quizzed.

The report adds accuracy by kind of fact and a table of the probes. Quizzes
run after turns 40, 80 and 120.

## Where things live

Each campaign is a folder under `campaigns/` (ignored by git):

| File | What it is |
| --- | --- |
| `canon.md` | Injected context: loaded into every turn. Starts from a fantasy template; dreaming rebuilds the story, threads, cast and contradictions. |
| `canon.prev.md` | The canon before the last dream, for comparing. |
| `wiki/tam.md` | One page per person, place, thing or group, written only by dreaming. |
| `dream_state.json` | How many turns have been dreamed, and the last recap. |
| `state.json` | Hit points, money (in copper), location, carried and stored items, flags. Updated by code only. |
| `transcripts/s001.jsonl` | One line per turn, with ids like `s001-t0004`. Tool calls are kept under `tools`. |
| `notes/n0001.md` | One saved fact per file. `unverified` until a dream marks it confirmed, wrong or unsupported. |
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
