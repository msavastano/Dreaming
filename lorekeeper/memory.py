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
        (self.folder / f"{note.id}.md").write_text(
            "---\n"
            f"id: {note.id}\n"
            f"turn: {note.turn}\n"
            f"status: {note.status}\n"
            f"about: {', '.join(note.about)}\n"
            f"created: {note.created}\n"
            "---\n"
            f"{note.text}\n"
        )
        return note

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
        )


def format_note(note: Note) -> str:
    about = f" (about: {', '.join(note.about)})" if note.about else ""
    return f"[{note.id}, from {note.turn}, {note.status}] {note.text}{about}"


@dataclass
class Hit:
    id: str
    kind: str  # "note" or "turn"
    text: str


def search(transcripts: Path, notes: NotesStore, query: str, limit: int = 6) -> list[Hit]:
    docs: list[Hit] = [Hit(n.id, "note", f"{n.text} (about: {', '.join(n.about)})" if n.about else n.text) for n in notes.all()]
    for t in load_all_turns(transcripts):
        docs.append(Hit(t["id"], "turn", f"Player: {t['player']}\nGM: {t['narration']}"))
    terms = [w for w in re.findall(r"[A-Za-z0-9']+", query.lower()) if len(w) > 1]
    if not terms or not docs:
        return []
    try:
        return _search_fts(docs, terms, limit)
    except sqlite3.OperationalError:  # this Python's SQLite was built without FTS5
        return _search_simple(docs, terms, limit)


def _search_fts(docs: list[Hit], terms: list[str], limit: int) -> list[Hit]:
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE VIRTUAL TABLE docs USING fts5(idx UNINDEXED, body, tokenize='porter')")
        db.executemany("INSERT INTO docs (idx, body) VALUES (?, ?)", [(i, d.text) for i, d in enumerate(docs)])
        match = " OR ".join(f'"{t}"' for t in terms)
        rows = db.execute(
            "SELECT idx FROM docs WHERE docs MATCH ? ORDER BY bm25(docs) LIMIT ?", (match, limit)
        ).fetchall()
    finally:
        db.close()
    return [docs[int(r[0])] for r in rows]


def _search_simple(docs: list[Hit], terms: list[str], limit: int) -> list[Hit]:
    scored = []
    for i, d in enumerate(docs):
        words = re.findall(r"[a-z0-9']+", d.text.lower())
        score = sum(words.count(t) for t in terms)
        if score:
            scored.append((-score, i))
    return [docs[i] for _, i in sorted(scored)[:limit]]


def format_hits(hits: list[Hit], max_chars: int = 700) -> str:
    if not hits:
        return "Nothing found."
    out = []
    for h in hits:
        text = h.text if len(h.text) <= max_chars else h.text[:max_chars].rstrip() + "..."
        out.append(f"[{h.kind} {h.id}]\n{text}")
    return "\n\n".join(out)
