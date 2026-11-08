"""Code checks on what dreaming writes, so the wiki can't drift from the transcript."""

from __future__ import annotations

import re
from difflib import SequenceMatcher


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def quote_found(quote: str, source: str, min_ratio: float = 0.8) -> bool:
    """True if `quote` appears in `source`, allowing small differences in punctuation or wording.

    The longest run the two share must cover at least `min_ratio` of the quote.
    """
    q, s = _norm(quote), _norm(source)
    if len(q.split()) < 2 or not s:
        return False
    if q in s:
        return True
    match = SequenceMatcher(None, q, s, autojunk=False).find_longest_match(0, len(q), 0, len(s))
    return match.size >= min_ratio * len(q)


def turn_text(turn: dict) -> str:
    return f"{turn.get('player', '')}\n{turn.get('narration', '')}"
