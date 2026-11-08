"""The wiki: the third memory layer. One Markdown page per person, place, thing or group.

Only dreaming writes pages. Each fact cites the turn it came from and a short
quote from that turn, so a fact can be checked against the transcript. During
play the game master sees only the one-line summary of each page (the cast list
in canon.md); search reaches the full pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

FACT_LINE = re.compile(r'^- (?P<text>.*?) \[(?P<turn>[^\]]+)\](?: "(?P<quote>.*)")?$')
KINDS = ("person", "place", "thing", "group")


@dataclass
class Fact:
    text: str
    turn: str
    quote: str = ""


@dataclass
class Page:
    name: str
    kind: str = "person"
    summary: str = ""
    aliases: list[str] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    updated: str = ""

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def names(self) -> list[str]:
        return [self.name] + self.aliases

    def mentioned_in(self, text: str) -> bool:
        return any(re.search(rf"\b{re.escape(n)}\b", text, re.I) for n in self.names() if len(n) > 2)

    def cast_line(self) -> str:
        return f"- {self.name} ({self.kind}): {self.summary}"

    def render(self) -> str:
        lines = ["---", f"name: {self.name}", f"kind: {self.kind}", f"aliases: {', '.join(self.aliases)}",
                 f"summary: {self.summary}", f"updated: {self.updated}", "---", "", "## Facts"]
        for f in self.facts:
            quote = f' "{f.quote}"' if f.quote else ""
            lines.append(f"- {f.text} [{f.turn}]{quote}")
        if self.contradictions:
            lines += ["", "## Contradictions"] + [f"- {c}" for c in self.contradictions]
        return "\n".join(lines) + "\n"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "page"


def parse_page(raw: str) -> Page:
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---\n"):
        header, _, body = raw[4:].partition("\n---\n")
        for line in header.splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    page = Page(
        name=meta.get("name", "?"),
        kind=meta.get("kind", "person"),
        summary=meta.get("summary", ""),
        aliases=[a.strip() for a in meta.get("aliases", "").split(",") if a.strip()],
        updated=meta.get("updated", ""),
    )
    section = None
    for line in body.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
        elif line.startswith("- ") and section == "facts":
            m = FACT_LINE.match(line)
            if m:
                page.facts.append(Fact(m["text"], m["turn"], m["quote"] or ""))
        elif line.startswith("- ") and section == "contradictions":
            page.contradictions.append(line[2:].strip())
    return page


class WikiStore:
    def __init__(self, folder: Path):
        self.folder = folder

    def all(self) -> list[Page]:
        if not self.folder.exists():
            return []
        return sorted((parse_page(p.read_text()) for p in self.folder.glob("*.md")), key=lambda p: p.name.lower())

    def find(self, name: str) -> Page | None:
        key = slugify(name)
        for page in self.all():
            if page.slug == key or key in (slugify(a) for a in page.aliases):
                return page
        return None

    def save(self, page: Page, old_slug: str | None = None) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        if old_slug and old_slug != page.slug:
            (self.folder / f"{old_slug}.md").unlink(missing_ok=True)
        (self.folder / f"{page.slug}.md").write_text(page.render())
