"""Play Lorekeeper in your browser.

    python -m lorekeeper.web                       # default campaign, opens http://127.0.0.1:8765
    python -m lorekeeper.web --campaign quest2 --provider claude
    python -m lorekeeper.web --port 9000 --no-browser

The page talks to a small local server that runs the same game as the terminal
version. It only listens on this computer (127.0.0.1). Nothing extra to install.
"""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import gm
from .config import load_config
from .llm import Budgeted, BudgetExceeded, make_provider
from .memory import search
from .play import ROOT, Campaign, Game
from .state import format_money
from .transcript import load_all_turns, load_window

STATIC = Path(__file__).resolve().parent / "static"
RECENT_TURNS = 200  # turns the page shows on load; older ones stay in the transcript files


class GameServer:
    """Everything the page needs, as plain dicts. One lock, so turns never overlap."""

    def __init__(self, game: Game, config: dict, name: str, provider: str, dream_llm_factory=None):
        self.game = game
        self.config = config
        self.name = name
        self.provider = provider
        self.dream_llm_factory = dream_llm_factory
        self.lock = threading.Lock()

    # --- reads -------------------------------------------------------------

    def snapshot(self) -> dict:
        from .dream import load_dream_state, undreamed_turns

        c = self.game.campaign
        cfg = self.config["narration"]
        turns = load_all_turns(c.transcripts)
        window = {t["id"] for t in load_window(c.transcripts, cfg["window_turns"], cfg["window_step"])}
        today = c.usage.totals(datetime.now(timezone.utc).date().isoformat())
        return {
            "campaign": self.name,
            "provider": self.provider,
            "session": self.game.transcript.session,
            "state": self.game.state,
            "purse": format_money(self.game.state.get("copper", 0)),
            "turns": [_turn(t, t["id"] in window) for t in turns[-RECENT_TURNS:]],
            "turn_count": len(turns),
            "notes": [_note(n) for n in c.notes.all()],
            "wiki": [_page_line(p) for p in sorted(c.wiki.all(), key=lambda p: (p.kind, p.name.lower()))],
            "canon": c.canon_path.read_text(),
            "recap": load_dream_state(c).get("recap", ""),
            "undreamed": len(undreamed_turns(c)),
            "usage": {"today": today, "total": c.usage.totals(), "cap": self.config["budget"]["daily_token_cap"]},
        }

    def page(self, slug: str) -> dict | None:
        page = next((p for p in self.game.campaign.wiki.all() if p.slug == slug), None)
        if page is None:
            return None
        return {**_page_line(page), "aliases": page.aliases, "updated": page.updated,
                "facts": [{"text": f.text, "turn": f.turn, "quote": f.quote} for f in page.facts],
                "contradictions": page.contradictions}

    def search(self, query: str) -> list[dict]:
        c = self.game.campaign
        return [{"id": h.id, "kind": h.kind, "text": h.text}
                for h in search(c.transcripts, c.notes, query, wiki=c.wiki)]

    # --- writes ------------------------------------------------------------

    def play(self, move: str) -> dict:
        with self.lock:
            try:
                turn = self.game.take_turn(move)
            except BudgetExceeded as e:
                return {"error": str(e)}
            reply = self.game.last_reply
            return {
                "narration": turn.narration,
                "parse_error": turn.parse_error,
                "tokens": None if reply is None else {
                    "input": reply.input_tokens, "cached": reply.cached_tokens,
                    "output": reply.output_tokens, "calls": reply.calls},
                **self.snapshot(),
            }

    def dream(self) -> dict:
        from .dream import DreamError, dream, format_dream, make_dream_llm

        with self.lock:
            c = self.game.campaign
            try:
                factory = self.dream_llm_factory or (lambda: make_dream_llm(self.config, c.usage))
                result = dream(c, factory(), gm.load_rules(ROOT / "prompts", "dream.md"), self.config, force=True)
            except (DreamError, BudgetExceeded) as e:
                return {"error": str(e), **self.snapshot()}
            except Exception as e:  # usually a missing API key for the dream provider
                return {"error": f"Could not dream: {e}", **self.snapshot()}
            if result is None:
                return {"report": "Nothing new to dream about yet.", **self.snapshot()}
            self.game.reload_canon()
            return {"report": format_dream(result), **self.snapshot()}


def _turn(t: dict, in_window: bool) -> dict:
    tools = [c for c in t.get("tools", []) if c.get("name") in ("remember", "search_memory")]
    return {
        "id": t["id"], "player": t["player"], "narration": t["narration"], "in_window": in_window,
        "recalled": t.get("recalled", []),
        "remembered": [c["args"].get("fact", "") for c in tools if c["name"] == "remember"],
        "searched": [c["args"].get("query", "") for c in tools if c["name"] == "search_memory"],
    }


def _note(n) -> dict:
    return {"id": n.id, "text": n.text, "turn": n.turn, "status": n.status, "about": list(n.about),
            "correction": n.correction}


def _page_line(p) -> dict:
    return {"slug": p.slug, "name": p.name, "kind": p.kind, "summary": p.summary, "facts_count": len(p.facts)}


def make_handler(server: GameServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the terminal quiet
            pass

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: int = 200) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return {}

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/campaign":
                self._json(server.snapshot())
            elif path.startswith("/api/wiki/"):
                page = server.page(unquote(path[len("/api/wiki/"):]))
                self._json(page if page else {"error": "No such page."}, 200 if page else 404)
            else:
                self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            body = self._body()
            try:
                if path == "/api/turn":
                    move = str(body.get("move", "")).strip()
                    self._json(server.play(move) if move else {"error": "Type a move first."})
                elif path == "/api/dream":
                    self._json(server.dream())
                elif path == "/api/search":
                    self._json({"hits": server.search(str(body.get("query", "")))})
                else:
                    self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            except Exception as e:  # an API error shouldn't kill the server
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play Lorekeeper in your browser.")
    parser.add_argument("--campaign", default="default", help="campaign name (a folder under campaigns/)")
    parser.add_argument("--provider", choices=["gemini", "claude"], help="override the narration provider")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="don't open the page automatically")
    parser.add_argument("--config", type=Path, default=ROOT / "config.toml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    name = args.provider or config["narration"]["provider"]
    campaign = Campaign(ROOT / "campaigns" / args.campaign)
    try:
        provider = make_provider(config, args.provider)
    except Exception as e:  # usually a missing API key
        print(f"Could not start the {name} model: {e}")
        print("Set GEMINI_API_KEY (Gemini) or ANTHROPIC_API_KEY (Claude) and try again.")
        return 1
    game = Game(campaign, Budgeted(provider, campaign.usage, config["budget"]["daily_token_cap"]),
                gm.load_rules(ROOT / "prompts"), config)
    server = GameServer(game, config, args.campaign, name)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(server))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Lorekeeper is running at {url}  (campaign '{args.campaign}', narrated by {name})")
    print("Press Ctrl+C here to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()
    from .dream import undreamed_turns
    from .play import format_usage, run_dream

    if config["dream"]["on_quit"] and len(undreamed_turns(campaign)) >= config["dream"]["min_turns"]:
        run_dream(game, config, force=False)
    print(format_usage(campaign.usage))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
