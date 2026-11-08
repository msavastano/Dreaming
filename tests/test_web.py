import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from lorekeeper import gm
from lorekeeper.config import load_config
from lorekeeper.llm import Budgeted
from lorekeeper.play import Campaign, Game
from lorekeeper.web import GameServer, make_handler
from lorekeeper.wiki import Fact, Page

from test_core import FakeProvider, reply_json
from test_dream import dream_json


def start(tmp_path, steps):
    campaign = Campaign(tmp_path / "camp")
    provider = FakeProvider(list(steps))
    llm = Budgeted(provider, campaign.usage, 100_000)
    config = load_config(None)
    game = Game(campaign, llm, "RULES", config)
    server = GameServer(game, config, "camp", "fake", dream_llm_factory=lambda: llm)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(server))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return campaign, httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def call(url, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as res:
            raw = res.read()
            return res.status, (json.loads(raw) if res.headers["Content-Type"].startswith("application/json") else raw)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_play_a_turn_and_read_memory(tmp_path):
    campaign, httpd, base = start(tmp_path, [reply_json("Hobb nods.", location="Crooked Lantern"), dream_json()])
    try:
        status, page = call(base + "/")
        assert status == 200 and b"Lorekeeper" in page

        status, snap = call(base + "/api/campaign")
        assert snap["turns"] == [] and snap["state"]["hero"]["name"] == "Wren" and snap["undreamed"] == 0

        status, out = call(base + "/api/turn", {"move": "I tell Hobb I grew up in Saltmere."})
        assert out["narration"] == "Hobb nods." and out["state"]["location"] == "Crooked Lantern"
        assert out["turns"][0]["player"] == "I tell Hobb I grew up in Saltmere." and out["turns"][0]["in_window"]
        assert out["undreamed"] == 1 and out["usage"]["today"]["calls"] == 1

        assert call(base + "/api/turn", {"move": "  "})[1] == {"error": "Type a move first."}

        hits = call(base + "/api/search", {"query": "Saltmere"})[1]["hits"]
        assert hits and hits[0]["id"] == "s001-t0001"

        out = call(base + "/api/dream", {})[1]
        assert out["report"].startswith("Dreamed over 1 turns") and out["undreamed"] == 0
        assert "Wren reached Thornwick." in out["canon"]

        campaign.wiki.save(Page("Tam", "person", "Stable boy.", [], [Fact("Tam is twelve.", "s001-t0001", "")]))
        page = call(base + "/api/wiki/tam")[1]
        assert page["name"] == "Tam" and page["facts"][0]["text"] == "Tam is twelve."
        assert call(base + "/api/wiki/nobody")[0] == 404
    finally:
        httpd.shutdown()


def test_an_api_error_is_reported_not_fatal(tmp_path):
    campaign, httpd, base = start(tmp_path, [])  # the fake has no replies left, so the turn raises
    try:
        status, out = call(base + "/api/turn", {"move": "I wait."})
        assert status == 500 and "error" in out
        assert call(base + "/api/campaign")[0] == 200  # still serving
    finally:
        httpd.shutdown()
