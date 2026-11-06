"""Party raids over the real WebSocket route, with the engine verifying and grading."""

import random
import time

import pytest
from fastapi.testclient import TestClient

from reps_api import party
from reps_api.main import app


@pytest.fixture
def hub(monkeypatch):
    h = party.PartyHub(use_pool=False, rng=random.Random(5))
    monkeypatch.setattr(party, "HUB", h)
    return h


@pytest.fixture
def client(store, hub):
    with TestClient(app) as c:
        yield c


def _until(ws, pred, limit=40):
    for _ in range(limit):
        msg = ws.receive_json()
        if pred(msg):
            return msg
    raise AssertionError("expected message never arrived")


def _state(pred):
    return lambda m: m["type"] == "state" and pred(m["room"])


def _open(client, code, token):
    return client.websocket_connect(f"/api/party/{code}/ws?token={token}")


def _create(client, name="Samir"):
    r = client.post("/api/party", json={"course_id": "calc-1", "name": name})
    assert r.status_code == 200, r.text
    return r.json()


def _key(hub, code, player_id, wait_s=15):
    """The player's current question and its key, once the server has one ready."""
    deadline = time.time() + wait_s
    while time.time() < deadline:
        p = hub.rooms[code].players[player_id]
        if p.question is not None and not p.busy:
            return p.question.id, p.question.answer
        time.sleep(0.02)
    raise AssertionError("no question arrived")


def test_create_join_and_preview(client, hub):
    host = _create(client)
    assert len(host["code"]) == party.CODE_LEN and set(host["code"]) <= set(party.CODE_ALPHABET)
    a = client.post(f"/api/party/{host['code'].lower()}/join", json={"name": "Meg"}).json()
    b = client.post(f"/api/party/{host['code']}/join", json={"name": "meg"}).json()
    room = hub.rooms[host["code"]]
    assert {p.name for p in room.players.values()} == {"Samir", "Meg", "meg 2"}
    assert room.players[host["player_id"]].store is not None  # the creator's answers count here
    assert room.players[a["player_id"]].store is None and room.players[b["player_id"]].store is None
    preview = client.get(f"/api/party/{host['code']}").json()
    assert preview["players"] == 3 and preview["status"] == "lobby" and preview["course_name"] == "Calculus I"
    assert client.get("/api/party/QQQQ").status_code == 404
    assert client.post("/api/party", json={"course_id": "nope", "name": "x"}).status_code == 404
    assert client.post(f"/api/party/{host['code']}/join", json={"name": "   "}).status_code == 422


def test_bad_token_is_refused(client, hub):
    host = _create(client)
    with _open(client, host["code"], "not-the-token") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error" and msg["fatal"]


def test_raid_hits_misses_and_progress_only_for_the_host(client, hub, store):
    host = _create(client)
    code = host["code"]
    guest = client.post(f"/api/party/{code}/join", json={"name": "Meg"}).json()
    with _open(client, code, host["token"]) as hws, _open(client, code, guest["token"]) as gws:
        _until(hws, _state(lambda r: len(r["players"]) == 2))
        gws.send_json({"type": "start"})
        assert _until(gws, lambda m: m["type"] == "error")["message"].startswith("Only the host")

        hws.send_json({"type": "start"})
        active = _until(hws, _state(lambda r: r["status"] == "active"))["room"]
        assert active["hp"] == active["hp_start"] == party.HP_BASE + 2 * party.HP_PER_PLAYER
        assert active["you"]["question"]["id"] and "answer" not in active["you"]["question"]
        _until(gws, _state(lambda r: r["status"] == "active" and r["you"]["question"]))
        assert client.post(f"/api/party/{code}/join", json={"name": "Late"}).status_code == 409

        # Host hits.
        qid, key = _key(hub, code, host["player_id"])
        hws.send_json({"type": "answer", "question_id": qid, "answer": key})
        res = _until(hws, lambda m: m["type"] == "result")
        assert res["correct"] and res["damage"] in party.DAMAGE.values()  # no streak yet, so base damage only
        assert res["xp"] == 10 and res["mastery"]["after"] > res["mastery"]["before"]
        assert hub.rooms[code].hp == active["hp_start"] - res["damage"]

        # Guest misses: loses a heart, no XP or mastery written for them.
        events_before = store.one("select count(*) n from mastery_events")["n"]
        qid, _ = _key(hub, code, guest["player_id"])
        gws.send_json({"type": "answer", "question_id": qid, "answer": "424242"})
        res = _until(gws, lambda m: m["type"] == "result")
        assert not res["correct"] and res["hearts"] == party.HEARTS - 1 and res["xp"] == 0 and res["mastery"] is None
        assert store.one("select count(*) n from mastery_events")["n"] == events_before
        assert store.one("select count(*) n from xp_events where reason = 'party_hit'")["n"] == 1

        # Unreadable input costs nothing.
        qid, _ = _key(hub, code, guest["player_id"])
        gws.send_json({"type": "answer", "question_id": qid, "answer": "import os"})
        assert _until(gws, lambda m: m["type"] in ("unparseable", "result"))["type"] == "unparseable"
        assert hub.rooms[code].players[guest["player_id"]].hearts == party.HEARTS - 1

        # The host's screen hears about the guest's miss.
        feed = _until(hws, _state(lambda r: any(e["kind"] == "miss" for e in r["feed"])))["room"]["feed"]
        assert {"start", "hit", "miss"} <= {e["kind"] for e in feed} and "Meg missed" in feed[0]["text"]


def test_damage_grows_with_streak_and_a_streak_revives(client, hub):
    host = _create(client)
    code = host["code"]
    guest = client.post(f"/api/party/{code}/join", json={"name": "Meg"}).json()
    with _open(client, code, host["token"]) as hws, _open(client, code, guest["token"]) as gws:
        hws.send_json({"type": "start"})
        _until(gws, _state(lambda r: r["status"] == "active" and r["you"]["question"]))
        for _ in range(party.HEARTS):
            qid, _ = _key(hub, code, guest["player_id"])
            gws.send_json({"type": "answer", "question_id": qid, "answer": "424242"})
            _until(gws, lambda m: m["type"] == "result")
        room = hub.rooms[code]
        assert room.players[guest["player_id"]].hearts == 0 and room.status == "active"

        damages = []
        for _ in range(party.REVIVE_EVERY):
            qid, key = _key(hub, code, host["player_id"])
            hws.send_json({"type": "answer", "question_id": qid, "answer": key})
            res = _until(hws, lambda m: m["type"] == "result")
            damages.append(res["damage"])
        # Each answer in the streak adds COMBO_STEP on top of the difficulty's base damage.
        bonuses = [d - min(party.DAMAGE.values()) for d in damages]
        assert bonuses[1] >= party.COMBO_STEP and bonuses[2] >= 2 * party.COMBO_STEP
        assert room.players[guest["player_id"]].hearts == 1
        _key(hub, code, guest["player_id"])  # back in with a fresh question
        revived = _until(gws, _state(lambda r: any(e["kind"] == "revive" for e in r["feed"])))["room"]
        assert next(p for p in revived["players"] if p["name"] == "Meg")["hearts"] == 1


def test_victory_pays_once_and_unlocks_party_up(client, hub, store):
    host = _create(client)
    code = host["code"]
    with _open(client, code, host["token"]) as ws:
        ws.send_json({"type": "start"})
        _until(ws, _state(lambda r: r["status"] == "active"))
        hub.rooms[code].hp = 1
        qid, key = _key(hub, code, host["player_id"])
        ws.send_json({"type": "answer", "question_id": qid, "answer": key})
        over = _until(ws, _state(lambda r: r["status"] == "over"))["room"]
        assert over["outcome"] == "victory" and over["hp"] == 0
        assert over["you"]["xp"] == 10 + 15 + 40
        reasons = {r["reason"] for r in store.all("select reason from xp_events")}
        assert {"party_hit", "party_finished", "party_cleared"} <= reasons

        ws.send_json({"type": "again"})
        lobby = _until(ws, _state(lambda r: r["status"] == "lobby"))["room"]
        assert lobby["players"][0]["damage"] == 0 and lobby["players"][0]["hearts"] == party.HEARTS
    listing = client.get("/api/achievements").json()
    listing = listing["achievements"] if isinstance(listing, dict) else listing
    keys = {a["key"] for a in listing if a["unlocked_at"]}
    assert "party_1" in keys


def test_everyone_down_is_a_wipe(client, hub, store):
    host = _create(client)
    code = host["code"]
    with _open(client, code, host["token"]) as ws:
        ws.send_json({"type": "start"})
        for _ in range(party.HEARTS):
            qid, _ = _key(hub, code, host["player_id"])
            ws.send_json({"type": "answer", "question_id": qid, "answer": "424242"})
            _until(ws, lambda m: m["type"] == "result")
        over = _until(ws, _state(lambda r: r["status"] == "over"))["room"]
        assert over["outcome"] == "wiped"
    assert store.one("select count(*) n from xp_events where reason = 'party_cleared'")["n"] == 0
    assert store.one("select count(*) n from xp_events where reason = 'party_finished'")["n"] == 1


def test_clock_runs_out(client, hub, monkeypatch):
    monkeypatch.setattr(party, "DURATION_S", 0.3)
    host = _create(client)
    with _open(client, host["code"], host["token"]) as ws:
        ws.send_json({"type": "start"})
        started = time.time()
        over = _until(ws, _state(lambda r: r["status"] == "over"))["room"]
        assert over["outcome"] == "timeout" and time.time() - started < 10


def test_host_leaving_the_lobby_hands_over(client, hub):
    host = _create(client)
    code = host["code"]
    guest = client.post(f"/api/party/{code}/join", json={"name": "Meg"}).json()
    with _open(client, code, guest["token"]) as gws:
        with _open(client, code, host["token"]) as hws:
            hws.send_json({"type": "leave"})
        room = _until(gws, _state(lambda r: len(r["players"]) == 1))["room"]
        assert room["you"]["is_host"]


def test_party_raid_on_a_boss_built_from_notes(client, hub, store):
    from reps_api import generation
    from reps_api.ingest.pdf import extract_text

    notes = (
        "Cell Biology\n\nOsmosis is the diffusion of water across a selectively permeable membrane. "
        "A hypertonic solution has a higher solute concentration than the cell, so water leaves the cell. "
        "Active transport moves molecules against their concentration gradient and requires ATP. "
        "Passive transport does not require ATP because molecules move down their concentration gradient. "
        "Enzymes are proteins that speed up chemical reactions by lowering the activation energy. "
        "Each enzyme has an active site that binds a specific substrate."
    )
    course_id = generation.generate_course(store, None, "Bio", extract_text(notes), "j", "d")["course_id"]
    r = client.post("/api/party", json={"course_id": course_id, "name": "Samir"}).json()
    with _open(client, r["code"], r["token"]) as ws:
        ws.send_json({"type": "start"})
        state = _until(ws, _state(lambda s: s["status"] == "active" and s["you"]["question"]))["room"]
        q = state["you"]["question"]
        assert q["kind"] == "recall" and q["checks"][0].startswith("quoted from your notes")
        qid, key = _key(hub, r["code"], r["player_id"])
        ws.send_json({"type": "answer", "question_id": qid, "answer": key})
        res = _until(ws, lambda m: m["type"] == "result")
        assert res["correct"] and res["damage"] > 0 and "From your notes" in res["method"]
