"""Notes and search: the second memory layer, plus a way to reach the first.

Notes are small Markdown files the game master writes during play with the
`remember` tool, one fact each. Each note records the turn it came from and a
status. Every note starts "unverified"; dreaming (milestone 3) checks notes
against the transcript and marks them confirmed or wrong.

Search covers notes and every transcript turn. It builds a throwaway SQLite
full-text index on each call, which is fast for campaigns of a few thousand
turns and means there is no index to keep in sync. No embeddings, no API calls.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .transcript import load_all_turns

NOTE_FILE = re.compile(r"n(\d+)\.md$")


@dataclass
class Note:
    id: str
    text: str
    turn: str
    status: str = "unverified"
    about: tuple[str, ...] = ()
    created: str = ""
    correction: str = ""


class NotesStore:
    def __init__(self, folder: Path):
        self.folder = folder

    def all(self) -> list[Note]:
        if not self.folder.exists():
            return []
        notes = [self._read(p) for p in self.folder.glob("n*.md") if NOTE_FILE.search(p.name)]
        return sorted(notes, key=lambda n: n.id)

    def add(self, text: str, about: list[str], turn: str) -> Note:
        self.folder.mkdir(parents=True, exist_ok=True)
        numbers = [int(NOTE_FILE.search(p.name).group(1)) for p in self.folder.glob("n*.md") if NOTE_FILE.search(p.name)]
        note = Note(
            id=f"n{max(numbers, default=0) + 1:04d}",
            text=" ".join(text.split()),
            turn=turn,
            about=tuple(a.strip() for a in about if a.strip()),
            created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self._write(note)
        return note

    def set_status(self, note_id: str, status: str, correction: str = "") -> None:
        """Dreaming marks each note confirmed, wrong or unsupported."""
        path = self.folder / f"{note_id}.md"
        if not path.exists():
            return
        note = self._read(path)
        note.status = status
        note.correction = " ".join(correction.split())
        self._write(note)

    def _write(self, note: Note) -> None:
        correction = f"correction: {note.correction}\n" if note.correction else ""
        (self.folder / f"{note.id}.md").write_text(
            "---\n"
            f"id: {note.id}\n"
            f"turn: {note.turn}\n"
            f"status: {note.status}\n"
            f"about: {', '.join(note.about)}\n"
            f"created: {note.created}\n"
            f"{correction}"
            "---\n"
            f"{note.text}\n"
        )

    @staticmethod
    def _read(path: Path) -> Note:
        raw = path.read_text()
        meta: dict[str, str] = {}
        body = raw
        if raw.startswith("---\n"):
            header, _, body = raw[4:].partition("\n---\n")
            for line in header.splitlines():
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        return Note(
            id=meta.get("id", path.stem),
            text=body.strip(),
            turn=meta.get("turn", ""),
            status=meta.get("status", "unverified"),
            about=tuple(a.strip() for a in meta.get("about", "").split(",") if a.strip()),
            created=meta.get("created", ""),
            correction=meta.get("correction", ""),
        )


def format_note(note: Note) -> str:
    about = f" (about: {', '.join(note.about)})" if note.about else ""
    fix = f" Correction: {note.correction}" if note.correction else ""
    return f"[{note.id}, from {note.turn}, {note.status}] {note.text}{about}{fix}"


@dataclass
class Hit:
    id: str
    kind: str  # "note", "turn" or "wiki"
    text: str


# Common words that would match nearly every turn.
STOPWORDS = frozenset("""
a an and are as at be but by did do does for from had has have he her him his how i if in into is it its
me my no not of on or our she so than that the their them then there they this to too up was we were
what when where which who why will with you your yours i'm it's don't
""".split())


def search(transcripts: Path, notes: NotesStore, query: str, limit: int = 6,
           exclude: set[str] | frozenset[str] = frozenset(), min_terms: int = 1, wiki=None) -> list[Hit]:
    """Notes and turns that match `query`, best first.

    `exclude` skips ids the caller already has (turns in the window, notes in the
    prompt). `min_terms` keeps only results that match at least that many of the
    query's words, which filters out weak matches for automatic recall. Notes that
    dreaming marked wrong or unsupported are left out, except a wrong note's correction.
    """
    docs: list[Hit] = []
    for n in notes.all():
        if n.id in exclude:
            continue
        if n.status in ("wrong", "unsupported"):
            # Dreaming rejected this note. Only its correction, if any, is worth finding.
            if n.status == "wrong" and n.correction:
                docs.append(Hit(n.id, "note", f"Correction: {n.correction}"))
            continue
        docs.append(Hit(n.id, "note", f"{n.text} (about: {', '.join(n.about)})" if n.about else n.text))
    if wiki is not None:
        for page in wiki.all():
            if page.slug not in exclude:
                facts = " ".join(f.text for f in page.facts)
                docs.append(Hit(page.slug, "wiki", f"{page.name} ({page.kind}): {page.summary} {facts}"))
    for t in load_all_turns(transcripts):
        if t["id"] not in exclude:
            docs.append(Hit(t["id"], "turn", f"Player: {t['player']}\nGM: {t['narration']}"))
    words = re.findall(r"[a-z0-9]+", query.lower().replace("'s", ""))
    terms = list(dict.fromkeys(w for w in words if len(w) > 1 and w not in STOPWORDS))
    if not terms or not docs:
        return []
    need = min(min_terms, len(terms))
    try:
        return _search_fts(docs, terms, limit, need)
    except sqlite3.OperationalError:  # this Python's SQLite was built without FTS5
        return _search_simple(docs, terms, limit, need)


def _search_fts(docs: list[Hit], terms: list[str], limit: int, need: int = 1) -> list[Hit]:
    """Rank exact-phrase matches first, then turns with every word, then any word."""
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE VIRTUAL TABLE docs USING fts5(idx UNINDEXED, body, tokenize='porter')")
        db.executemany("INSERT INTO docs (idx, body) VALUES (?, ?)", [(i, d.text) for i, d in enumerate(docs)])

        def run(match: str, n: int | None = None) -> list[int]:
            sql = "SELECT idx FROM docs WHERE docs MATCH ? ORDER BY bm25(docs)"
            rows = db.execute(sql + (" LIMIT ?" if n else ""), (match, n) if n else (match,)).fetchall()
            return [int(r[0]) for r in rows]

        quoted = [f'"{t}"' for t in terms]
        allowed = None
        if need > 1:
            counts: dict[int, int] = {}
            for q in quoted:
                for i in run(q):
                    counts[i] = counts.get(i, 0) + 1
            allowed = {i for i, c in counts.items() if c >= need}
        queries = [" OR ".join(quoted)]
        if len(terms) > 1:
            queries = ['"' + " ".join(terms) + '"', " AND ".join(quoted)] + queries
        found: list[int] = []
        for match in queries:
            for i in run(match):
                if i not in found and (allowed is None or i in allowed):
                    found.append(i)
            if len(found) >= limit:
                break
    finally:
        db.close()
    return [docs[i] for i in found[:limit]]


def _search_simple(docs: list[Hit], terms: list[str], limit: int, need: int = 1) -> list[Hit]:
    phrase = " ".join(terms)
    scored = []
    for i, d in enumerate(docs):
        words = re.findall(r"[a-z0-9]+", d.text.lower())
        present = [t for t in terms if t in words]
        if len(present) < max(need, 1):
            continue
        exact = len(terms) > 1 and phrase in " ".join(words)
        scored.append((-exact, -len(present), -sum(words.count(t) for t in terms), i))
    return [docs[s[-1]] for s in sorted(scored)[:limit]]


def format_hits(hits: list[Hit], max_chars: int = 700) -> str:
    if not hits:
        return "Nothing found."
    out = []
    for h in hits:
        text = h.text if len(h.text) <= max_chars else h.text[:max_chars].rstrip() + "..."
        out.append(f"[{h.kind} {h.id}]\n{text}")
    return "\n\n".join(out)
