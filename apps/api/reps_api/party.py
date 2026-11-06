"""Party raids: friends on one Reps server fight a shared boss in real time.

Rooms live in memory in the API process and talk to browsers over a WebSocket.
Each player gets their own questions, generated and verified by the same engine
as solo fights, and every answer is graded on the server by SymPy. The client
only ever sends "start", "answer", "again" and "leave"; damage, hearts and the
outcome are decided here.

Whose progress counts: a player with a store attached gets XP and mastery
updates. In local mode that is the room's creator (the person whose computer is
running Reps); guests play for the leaderboard. With accounts turned on, every
signed-in player gets their own store.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import secrets
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from . import exam
from .content.courses import QuestionTemplate
from .progression import XP_RULES, award
from .store import Store, dumps, new_id
from .verification.math_engine import MathTask, display_latex
from .verification.status import VerificationStatus
from .verification.timeouts import VerificationTimeout

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I or O, so codes read cleanly aloud
CODE_LEN = 4
MAX_PLAYERS = 8
NAME_MAX = 20
HEARTS = 3
HP_BASE = 20
HP_PER_PLAYER = 60
DURATION_S = 360
DAMAGE = {1: 8, 2: 11, 3: 14}
COMBO_STEP = 2  # extra damage per answer already in the streak
COMBO_CAP = 6
REVIVE_EVERY = 3  # a streak of this length brings back a downed teammate
FEED_LEN = 40
ROOM_IDLE_S = 3600


class PartyError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Question:
    id: str
    topic_id: str
    topic: str
    template_id: str
    difficulty: int
    prompt: str
    latex: str | None
    task: MathTask
    answer: str
    answer_latex: str | None
    rel_tol: float | None
    seed: int
    answer_format: str
    method: str | None
    checks: list[str]

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic_id": self.topic_id,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "prompt": self.prompt,
            "latex": self.latex,
            "answer_format": self.answer_format,
            "checks": self.checks,
        }


@dataclass
class Player:
    id: str
    name: str
    token: str
    is_host: bool
    store: Store | None  # where this player's XP and mastery go; None for guests
    hearts: int = HEARTS
    damage: int = 0
    answered: int = 0
    correct: int = 0
    combo: int = 0
    best_combo: int = 0
    xp: int = 0
    question: Question | None = None
    busy: bool = False
    downed_at: float | None = None
    recent_topics: list[str] = field(default_factory=list)
    recent_templates: list[str] = field(default_factory=list)
    sockets: set[WebSocket] = field(default_factory=set)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "is_host": self.is_host,
            "hearts": self.hearts,
            "damage": self.damage,
            "answered": self.answered,
            "correct": self.correct,
            "combo": self.combo,
            "best_combo": self.best_combo,
            "down": self.hearts <= 0,
            "connected": bool(self.sockets),
        }


@dataclass
class Room:
    code: str
    course_id: str
    course_name: str
    boss_name: str
    topics: dict[str, str]  # topic id -> name, only topics with templates
    templates: dict[str, list[tuple[str, QuestionTemplate]]]
    store: Store
    status: str = "lobby"  # lobby | starting | active | over
    outcome: str | None = None  # victory | wiped | timeout
    hp: int = 0
    hp_start: int = 0
    started_at: float | None = None
    ends_at: float | None = None
    players: dict[str, Player] = field(default_factory=dict)
    feed: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=FEED_LEN))
    touched: float = field(default_factory=time.time)
    round: int = 0
    timer: asyncio.Task[None] | None = None

    def event(self, kind: str, text: str, **extra: Any) -> None:
        self.feed.appendleft({"id": new_id(), "kind": kind, "text": text, "at": time.time(), **extra})

    def view(self, viewer: Player | None) -> dict[str, Any]:
        board = sorted(self.players.values(), key=lambda p: (-p.damage, -p.correct, p.name.lower()))
        out: dict[str, Any] = {
            "code": self.code,
            "course_id": self.course_id,
            "course_name": self.course_name,
            "boss_name": self.boss_name,
            "topics": [{"id": k, "name": v} for k, v in self.topics.items()],
            "status": self.status,
            "outcome": self.outcome,
            "hp": self.hp,
            "hp_start": self.hp_start,
            "duration_s": DURATION_S,
            "ends_at": self.ends_at,
            "server_now": time.time(),
            "max_players": MAX_PLAYERS,
            "max_hearts": HEARTS,
            "players": [p.public() for p in board],
            "feed": list(self.feed),
            "rules": {
                "damage": DAMAGE,
                "combo_step": COMBO_STEP,
                "combo_cap": COMBO_CAP,
                "revive_every": REVIVE_EVERY,
                "hp_per_player": HP_PER_PLAYER,
            },
        }
        if viewer:
            out["you"] = {
                "id": viewer.id,
                "name": viewer.name,
                "is_host": viewer.is_host,
                "counts": viewer.store is not None,
                "hearts": viewer.hearts,
                "xp": viewer.xp,
                "busy": viewer.busy,
                "question": viewer.question.public() if viewer.question else None,
            }
        return out


def clean_name(name: str) -> str:
    name = " ".join(name.split())[:NAME_MAX]
    if not name:
        raise PartyError(422, "Pick a name first.")
    return name


def lan_addresses() -> list[str]:
    """IPv4 addresses other devices on the same network can use to reach this computer."""
    found: list[str] = []
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # no packet is sent; this only picks the outbound interface
        found.append(s.getsockname()[0])
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(str(info[4][0]))
    return [a for i, a in enumerate(found) if a not in found[:i] and not a.startswith("127.")]


class PartyHub:
    def __init__(self, use_pool: bool = True, rng: random.Random | None = None) -> None:
        self.rooms: dict[str, Room] = {}
        self.use_pool = use_pool
        self.rng = rng or random.Random()

    # ------------------------------------------------------------ rooms

    def _new_code(self) -> str:
        for _ in range(200):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
            if code not in self.rooms:
                return code
        raise PartyError(503, "Too many open rooms. Try again in a minute.")

    def _sweep(self) -> None:
        now = time.time()
        for code in [c for c, r in self.rooms.items() if now - r.touched > ROOM_IDLE_S and not any(p.sockets for p in r.players.values())]:
            room = self.rooms.pop(code)
            if room.timer:
                room.timer.cancel()

    def room(self, code: str) -> Room:
        room = self.rooms.get(code.upper())
        if not room:
            raise PartyError(404, "No raid with that code. Check the letters with your host.")
        return room

    def create(self, store: Store, course_id: str, name: str, player_store: Store | None) -> dict[str, Any]:
        self._sweep()
        course = store.one("select id, name, boss_name from courses where id = ? and id != ?", (course_id, exam.RAID_ID))
        if not course:
            raise PartyError(404, "Course not found.")
        topic_ids = exam.course_topic_ids(store, course_id)
        names = {t["id"]: t["name"] for t in exam.topic_view(store, topic_ids)}
        templates: dict[str, list[tuple[str, QuestionTemplate]]] = {}
        if topic_ids:
            marks = ",".join("?" * len(topic_ids))
            for row in store.all(f"select id, topic_id, body from templates where topic_id in ({marks})", tuple(topic_ids)):
                if not row["body"].lstrip().startswith('{"kind":"recall"'):  # party raids use computed questions only for now
                    templates.setdefault(row["topic_id"], []).append((row["id"], QuestionTemplate.model_validate_json(row["body"])))
        if not templates:
            raise PartyError(409, "This course has no verified question types yet.")
        room = Room(
            code=self._new_code(),
            course_id=course["id"],
            course_name=course["name"],
            boss_name=course["boss_name"],
            topics={t: names[t] for t in topic_ids if t in templates},
            templates=templates,
            store=store,
        )
        self.rooms[room.code] = room
        player = self._add(room, name, is_host=True, player_store=player_store)
        return {"code": room.code, "player_id": player.id, "token": player.token}

    def join(self, code: str, name: str, player_store: Store | None) -> dict[str, Any]:
        room = self.room(code)
        if room.status != "lobby":
            raise PartyError(409, "This raid already started. Ask the host to run it back, then join.")
        if len(room.players) >= MAX_PLAYERS:
            raise PartyError(409, f"This raid is full ({MAX_PLAYERS} players).")
        player = self._add(room, name, is_host=False, player_store=player_store)
        return {"code": room.code, "player_id": player.id, "token": player.token}

    def _add(self, room: Room, name: str, is_host: bool, player_store: Store | None) -> Player:
        name = clean_name(name)
        taken = {p.name.lower() for p in room.players.values()}
        base, n = name, 2
        while name.lower() in taken:
            suffix = f" {n}"
            name = base[: NAME_MAX - len(suffix)] + suffix
            n += 1
        player = Player(id=new_id(), name=name, token=secrets.token_urlsafe(18), is_host=is_host, store=player_store)
        room.players[player.id] = player
        room.touched = time.time()
        room.event("join", f"{name} joined.")
        return player

    def player_for(self, room: Room, token: str) -> Player:
        for p in room.players.values():
            if secrets.compare_digest(p.token, token):
                return p
        raise PartyError(403, "That seat belongs to someone else. Join the raid again.")

    def preview(self, code: str) -> dict[str, Any]:
        room = self.room(code)
        return {
            "code": room.code,
            "course_name": room.course_name,
            "boss_name": room.boss_name,
            "course_id": room.course_id,
            "status": room.status,
            "players": len(room.players),
            "max_players": MAX_PLAYERS,
        }

    # ------------------------------------------------------------ messaging

    async def broadcast(self, room: Room) -> None:
        for p in list(room.players.values()):
            await self.send(p, {"type": "state", "room": room.view(p)})

    async def send(self, player: Player, message: dict[str, Any]) -> None:
        text = dumps(message)
        for ws in list(player.sockets):
            try:
                await ws.send_text(text)
            except Exception:  # a closed tab; its own handler cleans up
                player.sockets.discard(ws)

    async def connect(self, room: Room, player: Player, ws: WebSocket) -> None:
        player.sockets.add(ws)
        room.touched = time.time()
        await self.broadcast(room)

    async def disconnect(self, room: Room, player: Player, ws: WebSocket) -> None:
        player.sockets.discard(ws)
        await self.broadcast(room)

    async def handle(self, room: Room, player: Player, message: dict[str, Any]) -> None:
        room.touched = time.time()
        kind = message.get("type")
        if kind == "start":
            await self.start(room, player)
        elif kind == "answer":
            await self.answer(room, player, str(message.get("question_id", "")), str(message.get("answer", ""))[:300])
        elif kind == "again":
            await self.again(room, player)
        elif kind == "leave":
            await self.leave(room, player)
        elif kind != "ping":
            await self.send(player, {"type": "error", "message": "Unknown message."})

    async def _error(self, player: Player, message: str) -> None:
        await self.send(player, {"type": "error", "message": message})

    # ------------------------------------------------------------ flow

    async def start(self, room: Room, player: Player) -> None:
        if not player.is_host:
            return await self._error(player, "Only the host can start the raid.")
        if room.status != "lobby":
            return await self._error(player, "The raid already started.")
        room.status = "starting"
        room.round += 1
        for p in room.players.values():
            self._reset(p)
        room.hp_start = room.hp = HP_BASE + HP_PER_PLAYER * len(room.players)
        room.event("start", f"{room.boss_name} appears with {room.hp} HP. {len(room.players)} in the party.")
        await self.broadcast(room)

        questions = await asyncio.gather(*(asyncio.to_thread(self._make_question, room, p) for p in room.players.values()), return_exceptions=True)
        for p, q in zip(list(room.players.values()), questions, strict=True):
            p.question = q if isinstance(q, Question) else None
            if p.question is None:
                await self._error(p, "Couldn't produce a verified question. The failure was logged.")
        room.status = "active"
        room.started_at = time.time()
        room.ends_at = room.started_at + DURATION_S
        room.timer = asyncio.create_task(self._clock(room, room.round))
        await self.broadcast(room)

    async def _clock(self, room: Room, round_no: int) -> None:
        await asyncio.sleep(max(0.0, (room.ends_at or time.time()) - time.time()))
        if room.status == "active" and room.round == round_no:
            await self._end(room, "timeout")

    async def again(self, room: Room, player: Player) -> None:
        if not player.is_host:
            return await self._error(player, "Only the host can run it back.")
        if room.status != "over":
            return
        room.status = "lobby"
        room.outcome = None
        room.hp = room.hp_start = 0
        room.started_at = room.ends_at = None
        for p in room.players.values():
            self._reset(p)
        room.event("lobby", "Back in the lobby. New friends can join now.")
        await self.broadcast(room)

    async def leave(self, room: Room, player: Player) -> None:
        if room.status in ("lobby", "over"):
            room.players.pop(player.id, None)
            room.event("leave", f"{player.name} left.")
            if player.is_host and room.players:
                heir = next(iter(room.players.values()))
                heir.is_host = True
                room.event("host", f"{heir.name} is the host now.")
            for ws in list(player.sockets):
                with contextlib.suppress(Exception):
                    await ws.close()
            player.sockets.clear()
            if not room.players:
                self.rooms.pop(room.code, None)
                return
        await self.broadcast(room)

    def _reset(self, p: Player) -> None:
        p.hearts, p.damage, p.answered, p.correct, p.combo, p.best_combo, p.xp = HEARTS, 0, 0, 0, 0, 0, 0
        p.question, p.busy, p.downed_at = None, False, None
        p.recent_topics.clear()
        p.recent_templates.clear()

    # ------------------------------------------------------------ questions

    def _make_question(self, room: Room, player: Player) -> Question:
        """Pick a topic the player hasn't just seen and a template near their streak's difficulty, then verify an instance."""
        rng = random.Random(self.rng.random())
        topics = list(room.templates)
        fresh = [t for t in topics if t not in player.recent_topics[-max(1, len(topics) - 1) :]] or topics
        topic_id = rng.choice(fresh)
        target = 1 + min(2, player.combo // 2)
        candidates = list(room.templates[topic_id])
        while candidates:
            template_id, tpl = exam._pick_template(candidates, target, player.recent_templates, rng)
            for _ in range(exam.MAX_INSTANCE_TRIES):
                seed = rng.randrange(1, 2**31)
                result = exam._verify(tpl.spec, seed, self.use_pool)
                exam._log_verification(room.store, template_id, result)
                if result.status is VerificationStatus.VERIFIED and result.instance and result.answer:
                    player.recent_topics.append(topic_id)
                    player.recent_templates.append(template_id)
                    return Question(
                        id=new_id(),
                        topic_id=topic_id,
                        topic=room.topics[topic_id],
                        template_id=template_id,
                        difficulty=tpl.difficulty,
                        prompt=result.instance.statement,
                        latex=display_latex(result.instance.task),
                        task=result.instance.task,
                        answer=result.answer,
                        answer_latex=result.answer_latex,
                        rel_tol=tpl.rel_tol,
                        seed=seed,
                        answer_format=tpl.answer_format,
                        method=exam._fill(tpl.method, result.instance.values),
                        checks=[c.method for c in result.checks],
                    )
            candidates = [c for c in candidates if c[0] != template_id]
        raise PartyError(503, "Couldn't produce a verified question for this topic.")

    async def _refill(self, room: Room, player: Player) -> None:
        try:
            q = await asyncio.to_thread(self._make_question, room, player)
        except Exception:
            await self._error(player, "Couldn't produce a verified question. The failure was logged.")
            return
        if room.status == "active" and player.hearts > 0:
            player.question = q
            await self.broadcast(room)

    # ------------------------------------------------------------ answers

    async def answer(self, room: Room, player: Player, question_id: str, text: str) -> None:
        q = player.question
        if room.status != "active":
            return await self._error(player, "The raid isn't running.")
        if player.hearts <= 0:
            return await self._error(player, "You're down. A teammate's streak can bring you back.")
        if player.busy or not q or q.id != question_id:
            return  # a double submit or a stale question; ignore it
        text = text.strip()
        if not text:
            return await self._error(player, "Type an answer first.")

        player.busy = True
        try:
            grade, _ = await asyncio.to_thread(exam._grade, q.task, {"answer": q.answer, "seed": q.seed, "rel_tol": q.rel_tol}, text, None, self.use_pool)
        except VerificationTimeout:
            player.busy = False
            return await self.send(player, {"type": "unparseable", "message": "Checking that answer took too long. Try a simpler form."})
        if grade.correct is None:
            player.busy = False
            return await self.send(player, {"type": "unparseable", "message": f"Couldn't read that answer ({grade.detail}). {q.answer_format}."})
        if room.status != "active" or player.question is not q:
            player.busy = False
            return

        correct = bool(grade.correct)
        player.answered += 1
        damage = 0
        revived: Player | None = None
        if correct:
            damage = DAMAGE.get(q.difficulty, DAMAGE[2]) + min(COMBO_CAP, COMBO_STEP * player.combo)
            player.combo += 1
            player.best_combo = max(player.best_combo, player.combo)
            player.correct += 1
            player.damage += damage
            room.hp = max(0, room.hp - damage)
            streak = f", {player.combo} streak" if player.combo >= 2 else ""
            room.event("hit", f"{player.name} hit for {damage} with {q.topic}{streak}.", player_id=player.id, damage=damage)
            if player.combo % REVIVE_EVERY == 0:
                downed = sorted((p for p in room.players.values() if p.hearts <= 0), key=lambda p: p.downed_at or 0)
                if downed:
                    revived = downed[0]
                    revived.hearts, revived.downed_at, revived.combo = 1, None, 0
                    room.event("revive", f"{player.name}'s streak brought {revived.name} back with 1 heart.", player_id=revived.id)
        else:
            player.combo = 0
            player.hearts -= 1
            room.event("miss", f"{player.name} missed {q.topic}.", player_id=player.id)
            if player.hearts <= 0:
                player.downed_at = time.time()
                room.event("down", f"{player.name} is down.", player_id=player.id)

        xp, mastery = 0, None
        if player.store is not None:
            xp, mastery = await asyncio.to_thread(self._record, player.store, room, q, correct)
            player.xp += xp

        player.question = None
        player.busy = False
        await self.send(
            player,
            {
                "type": "result",
                "question_id": q.id,
                "topic": q.topic,
                "correct": correct,
                "damage": damage,
                "hearts": player.hearts,
                "your_answer": text,
                "answer": q.answer,
                "answer_latex": q.answer_latex,
                "method": q.method,
                "graded_by": grade.method,
                "xp": xp,
                "mastery": mastery,
            },
        )

        if room.hp <= 0:
            await self._end(room, "victory")
            return
        if all(p.hearts <= 0 for p in room.players.values()):
            await self._end(room, "wiped")
            return
        await self.broadcast(room)
        refills = [self._refill(room, p) for p in (player, revived) if p is not None and p.hearts > 0 and p.question is None]
        await asyncio.gather(*refills)

    def _record(self, store: Store, room: Room, q: Question, correct: bool) -> tuple[int, dict[str, float] | None]:
        mastery = None
        if store.one("select 1 from topics where id = ?", (q.topic_id,)):
            before, after = exam.record_practice(store, q.topic_id, correct, q.difficulty)
            mastery = {"before": round(before, 3), "after": round(after, 3)}
        xp = award(store, "party_hit", XP_RULES["party_hit"], "party_question", q.id) if correct else 0
        return xp, mastery

    async def _end(self, room: Room, outcome: str) -> None:
        if room.status != "active":
            return
        room.status, room.outcome = "over", outcome
        if room.timer and room.timer is not asyncio.current_task():
            room.timer.cancel()
        text = {
            "victory": f"{room.boss_name} is down. The party wins.",
            "wiped": "Everyone is down. The boss wins this one.",
            "timeout": f"Time's up. {room.boss_name} escaped with {room.hp} HP.",
        }[outcome]
        room.event("end", text)
        source = f"{room.code}:{room.started_at}"
        for p in room.players.values():
            p.question = None
            if p.store is not None:
                xp = award(p.store, "party_finished", XP_RULES["party_finished"], "party_room", f"{source}:{p.id}")
                if outcome == "victory":
                    xp += award(p.store, "party_cleared", XP_RULES["party_cleared"], "party_room", f"{source}:{p.id}")
                p.xp += xp
        await self.broadcast(room)


HUB = PartyHub()
