"use client";

import { Check, Copy, Crown, Flag, HeartPulse, LogOut, RotateCcw, ShieldCheck, Skull, Sword, Swords, Timer, UserPlus, Users, X, Zap } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BossArt, type BossState } from "@/components/BossArt";
import { HurtVignette, ImpactBurst } from "@/components/Effects";
import { DifficultyPips, Hearts } from "@/components/Hud";
import { TeX } from "@/components/Math";
import { ErrorNote, Spinner } from "@/components/ui";
import { api, notifyProgress, type PartyEvent, type PartyPreview, type PartyRoom, type PartySeat } from "@/lib/api";
import { forgetSeat, saveSeat, savedSeat, useParty } from "@/lib/party";
import { play } from "@/lib/sound";

type Floater = { id: string; text: string; mine: boolean };

export default function PartyRoomPage() {
  const params = useParams<{ code: string }>();
  const code = params.code.toUpperCase();
  const [seat, setSeat] = useState<PartySeat | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    setSeat(savedSeat(code));
    setChecked(true);
  }, [code]);

  if (!checked) return <Spinner label="Finding your seat" />;
  if (!seat) return <JoinGate code={code} onJoined={setSeat} />;
  return <Room code={code} seat={seat} onLost={() => setSeat(null)} />;
}

// ---------------------------------------------------------------- join from a shared link

function JoinGate({ code, onJoined }: { code: string; onJoined: (s: PartySeat) => void }) {
  const [preview, setPreview] = useState<PartyPreview | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .partyPreview(code)
      .then(setPreview)
      .catch((e: Error) => setError(e.message));
  }, [code]);

  const join = async () => {
    setBusy(true);
    setError(null);
    try {
      const seat = await api.partyJoin(code, name.trim());
      saveSeat(seat);
      onJoined(seat);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <section className="panel p-6 text-center">
        {preview && <BossArt courseId={preview.course_id} name={preview.boss_name} className="mx-auto h-32 w-32" track />}
        <h1 className="h-display mt-2 text-2xl">{preview ? `Raid on ${preview.boss_name}` : `Raid ${code}`}</h1>
        {preview && (
          <p className="mt-1 text-sm text-muted">
            {preview.course_name}, {preview.players} of {preview.max_players} in the party
          </p>
        )}
        {error && (
          <div className="mt-4 text-left">
            <ErrorNote message={error} />
          </div>
        )}
        {preview && preview.status === "lobby" && (
          <form
            className="mt-6 text-left"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) void join();
            }}
          >
            <label htmlFor="gate-name" className="label">
              Your name
            </label>
            <input id="gate-name" className="field" value={name} maxLength={20} onChange={(e) => setName(e.target.value)} autoFocus />
            <button type="submit" className="btn-cyan mt-4 w-full py-3" disabled={!name.trim() || busy}>
              {busy ? "Joining" : "Join the raid"}
            </button>
          </form>
        )}
        {preview && preview.status !== "lobby" && <p className="mt-4 text-sm text-xp">This raid is underway. Ask the host to run it back, then join.</p>}
        <Link href="/party" className="mt-6 inline-block text-sm text-muted hover:text-text">
          Back to party raids
        </Link>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- the room

function Room({ code, seat, onLost }: { code: string; seat: PartySeat; onLost: () => void }) {
  const router = useRouter();
  const { room, link, fatal, note, setNote, result, setResult, send, serverNow } = useParty(code, seat);
  const [answer, setAnswer] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [bossState, setBossState] = useState<BossState>("idle");
  const [floaters, setFloaters] = useState<Floater[]>([]);
  const [bursts, setBursts] = useState<number[]>([]);
  const [hurt, setHurt] = useState<number | null>(null);
  const seen = useRef<Set<string> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const me = room?.you;
  const q = me?.question ?? null;

  // React to new feed events: teammates' hits float over the boss, your own get the big effects.
  useEffect(() => {
    if (!room) return;
    if (seen.current === null) {
      seen.current = new Set(room.feed.map((e) => e.id));
      return;
    }
    const fresh = room.feed.filter((e) => !seen.current!.has(e.id)).reverse();
    for (const e of fresh) {
      seen.current.add(e.id);
      if (e.kind === "hit") {
        const mine = e.player_id === me?.id;
        const name = room.players.find((p) => p.id === e.player_id)?.name ?? "";
        const f = { id: e.id, text: mine ? `−${e.damage}` : `${name} −${e.damage}`, mine };
        setFloaters((xs) => [...xs, f]);
        setTimeout(() => setFloaters((xs) => xs.filter((x) => x.id !== f.id)), 1300);
        setBossState("hit");
        setTimeout(() => setBossState("idle"), 450);
        if (!mine) play("tick");
      } else if (e.kind === "end") {
        play(room.outcome === "victory" ? "victory" : "defeat");
        setBossState(room.outcome === "victory" ? "defeated" : "victor");
      } else if (e.kind === "start") {
        setBossState("windup");
        setTimeout(() => setBossState("idle"), 540);
      }
    }
  }, [room, me?.id]);

  // Your own answer comes back.
  useEffect(() => {
    if (!result) return;
    setSending(false);
    if (result.correct) {
      play("hit");
      const b = Date.now();
      setBursts((xs) => [...xs, b]);
      setTimeout(() => setBursts((xs) => xs.filter((x) => x !== b)), 900);
    } else {
      play("miss");
      setBossState("attack");
      setHurt(Date.now());
      setTimeout(() => setBossState("idle"), 480);
      setTimeout(() => setHurt(null), 700);
    }
    if (result.xp) notifyProgress(result.xp);
  }, [result]);

  useEffect(() => {
    if (note) setSending(false);
  }, [note]);

  useEffect(() => {
    if (!answer.trim()) {
      setPreview(null);
      return;
    }
    const t = setTimeout(async () => {
      try {
        setPreview((await api.preview(answer)).latex);
      } catch {
        setPreview(null);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [answer]);

  useEffect(() => {
    if (q && !result) inputRef.current?.focus();
  }, [q, result]);
  useEffect(() => {
    if (result) nextRef.current?.focus();
  }, [result]);

  useEffect(() => {
    if (room?.status === "over") notifyProgress(0);
  }, [room?.status]);

  if (fatal)
    return (
      <div className="mx-auto max-w-md space-y-4">
        <ErrorNote message={fatal} />
        <button
          type="button"
          className="btn-ghost"
          onClick={() => {
            forgetSeat(code);
            onLost();
          }}
        >
          Join again
        </button>
      </div>
    );
  if (!room || !me) return <Spinner label={link === "retrying" ? "Reconnecting to the raid" : "Connecting to the raid"} />;

  const strike = (picked?: string) => {
    const given = picked ?? answer;
    if (!q || !given.trim() || sending) return;
    if (picked) setAnswer(picked);
    setNote(null);
    if (send({ type: "answer", question_id: q.id, answer: given })) setSending(true);
    else setNote("Lost the connection. Reconnecting, then try again.");
  };
  const next = () => {
    setResult(null);
    setAnswer("");
    setPreview(null);
  };
  const leave = () => {
    send({ type: "leave" });
    forgetSeat(code);
    router.push("/party");
  };

  const down = me.hearts <= 0;
  const self = room.players.find((p) => p.id === me.id);

  return (
    <div className="space-y-6">
      {hurt !== null && <HurtVignette key={hurt} />}
      {link !== "open" && (
        <div className="rounded-chip border border-xp/40 bg-xp/10 px-4 py-2 text-sm" role="status">
          Connection dropped. Reconnecting…
        </div>
      )}

      {room.status === "lobby" ? (
        <Lobby room={room} onStart={() => send({ type: "start" })} onLeave={leave} />
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <section className="panel relative flex flex-col overflow-hidden p-6" aria-label="Boss">
              <div className="pointer-events-none absolute inset-x-0 top-0 h-56 bg-[radial-gradient(ellipse_at_50%_0%,rgba(63,216,230,0.18),transparent_70%)]" />
              <div className="relative flex items-start justify-between gap-3">
                <div>
                  <p className="flex items-center gap-1.5 text-sm text-muted">
                    <Users size={14} aria-hidden /> Party raid {room.code}, {room.course_name}
                  </p>
                  <h1 className="h-display text-2xl">{room.boss_name}</h1>
                </div>
                <Clock room={room} serverNow={serverNow} />
              </div>
              <div className="relative mt-5">
                <SharedHp hp={room.hp} start={room.hp_start} />
              </div>
              <div className="relative mx-auto my-4 flex h-[220px] w-[220px] items-center justify-center xl:h-[260px] xl:w-[260px]">
                <BossArt
                  courseId={room.course_id}
                  name={room.boss_name}
                  state={room.status === "over" && bossState === "idle" ? (room.outcome === "victory" ? "defeated" : "victor") : bossState}
                  track={room.status === "active"}
                  className="h-full w-full"
                />
                {bursts.map((b) => (
                  <ImpactBurst key={b} count={12} spread={120} />
                ))}
                {floaters.map((f, i) => (
                  <div key={f.id} className="pointer-events-none absolute inset-x-0 flex justify-center" style={{ top: `${28 + (i % 3) * 12}%` }} aria-hidden>
                    <span
                      className={`animate-rise whitespace-nowrap font-display font-bold drop-shadow-[0_2px_6px_rgba(255,255,255,0.9)] ${f.mine ? "text-5xl text-xp" : "text-2xl text-cyan"}`}
                    >
                      {f.text}
                    </span>
                  </div>
                ))}
              </div>
              <div className="relative mt-auto flex flex-wrap items-center justify-between gap-4 border-t border-line pt-4">
                <Hearts hearts={me.hearts} max={room.max_hearts} />
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-display text-sm ${(self?.combo ?? 0) >= 2 ? "bg-xp/15 text-xp" : "text-muted"}`}
                >
                  <Zap size={15} className={(self?.combo ?? 0) >= 2 ? "fill-xp" : ""} aria-hidden />
                  {self?.combo ?? 0} streak
                  {(self?.combo ?? 0) > 0 && `, +${Math.min(room.rules.combo_cap, room.rules.combo_step * (self?.combo ?? 0))} dmg`}
                </span>
              </div>
            </section>

            <section className="panel relative flex flex-col overflow-hidden p-6 md:p-8 lg:min-h-[480px]" aria-label="Your question" aria-live="polite">
              {room.status === "over" && !result ? (
                <Results room={room} meId={me.id} counts={me.counts} xp={me.xp} onAgain={() => send({ type: "again" })} onLeave={leave} isHost={me.is_host} />
              ) : room.status === "starting" ? (
                <div className="m-auto">
                  <Spinner label={`${room.boss_name} is coming. Verifying everyone's first question`} />
                </div>
              ) : result ? (
                <div className="m-auto w-full max-w-xl animate-pop">
                  <div className={`rounded-panel border p-5 ${result.correct ? "border-heal/50 bg-heal/10" : "border-hp/50 bg-hp/10"}`} role="status">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <p className={`h-display text-3xl ${result.correct ? "text-heal" : "text-hp"}`}>{result.correct ? "Direct hit" : "Blocked"}</p>
                      <p className="text-sm text-muted">
                        {result.correct ? `−${result.damage} boss HP` : result.hearts > 0 ? "You lost a heart" : "You're down"}
                        {result.xp > 0 && <span className="ml-3 font-display font-semibold text-xp">+{result.xp} XP</span>}
                      </p>
                    </div>
                    <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[auto_1fr]">
                      <dt className="text-muted">You answered</dt>
                      <dd className="font-mono">{result.your_answer}</dd>
                      <dt className="text-muted">Answer</dt>
                      <dd>{result.answer_latex ? <TeX tex={result.answer_latex} /> : <span className="font-mono">{result.answer}</span>}</dd>
                      {result.method && (
                        <>
                          <dt className="text-muted">How</dt>
                          <dd>{result.method}</dd>
                        </>
                      )}
                      {result.mastery && (
                        <>
                          <dt className="text-muted">{result.topic}</dt>
                          <dd>
                            Mastery {Math.round(result.mastery.before * 100)}% to{" "}
                            <span className={`font-semibold ${result.mastery.after >= result.mastery.before ? "text-heal" : "text-hp"}`}>
                              {Math.round(result.mastery.after * 100)}%
                            </span>
                          </dd>
                        </>
                      )}
                    </dl>
                    <p className="mt-4 text-xs text-muted">Graded by {result.graded_by}, not by AI.</p>
                  </div>
                  <button ref={nextRef} type="button" className="btn-primary mt-5 w-full py-3" onClick={next}>
                    {room.status === "over" ? "See the result" : down ? "Watch the party" : "Next question"}
                    <span className="kbd">Enter</span>
                  </button>
                </div>
              ) : down ? (
                <div className="m-auto max-w-sm text-center">
                  <Skull size={40} className="mx-auto text-hp" aria-hidden />
                  <p className="h-display mt-3 text-3xl text-hp">You're down</p>
                  <p className="mt-2 text-muted">
                    Any teammate who lands a {room.rules.revive_every}-answer streak brings you back with one heart. Cheer them on.
                  </p>
                </div>
              ) : !q ? (
                <div className="m-auto">
                  <Spinner label="Verifying your next question" />
                </div>
              ) : (
                <div key={q.id} className="flex flex-1 animate-enter flex-col">
                  <div className="flex flex-wrap items-center gap-3 text-sm">
                    <span className="chip border-xp/50 text-xp">{q.topic}</span>
                    <DifficultyPips level={q.difficulty} />
                    <span className="text-muted">{room.rules.damage[String(q.difficulty)] ?? ""} dmg</span>
                    <span className="ml-auto inline-flex items-center gap-1.5 text-heal" title={`Answer key checked by: ${q.checks.join(", ")}`}>
                      <ShieldCheck size={15} aria-hidden /> {q.kind === "recall" ? "From your notes" : "Key verified"}
                    </span>
                  </div>
                  <p className="mt-6 text-lg leading-relaxed">{q.prompt}</p>
                  {q.latex && (
                    <div className="math-hero mt-5 overflow-x-auto rounded-panel border border-line bg-ink/60 px-6 py-8 text-center">
                      <TeX tex={q.latex} display />
                    </div>
                  )}
                  <form
                    className="mt-auto pt-8"
                    onSubmit={(e) => {
                      e.preventDefault();
                      strike();
                    }}
                  >
                    <p className="mb-2 text-sm text-muted">{q.answer_format}</p>
                    {q.choices?.length ? (
                      <div className="mb-3 grid gap-3 sm:grid-cols-2" role="group" aria-label="Choices">
                        {q.choices.map((c, i) => (
                          <button
                            key={c}
                            type="button"
                            disabled={sending || room.status !== "active"}
                            onClick={() => strike(c)}
                            className="flex min-h-[52px] items-center gap-3 rounded-panel border border-line bg-surface px-4 py-3 text-left shadow-card transition hover:-translate-y-0.5 hover:border-violet hover:bg-violet/[0.06] hover:shadow-lift disabled:opacity-60"
                          >
                            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-raised font-display text-sm text-muted">{i + 1}</span>
                            <span className="font-medium">{c}</span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                    <div className={q.choices?.length ? "hidden" : ""}>
                    <label htmlFor="party-answer" className="sr-only">
                      Your answer
                    </label>
                    <div className="flex flex-col gap-3 sm:flex-row">
                      <input
                        id="party-answer"
                        ref={inputRef}
                        className="field font-mono text-lg"
                        value={answer}
                        onChange={(e) => setAnswer(e.target.value)}
                        autoComplete="off"
                        spellCheck={false}
                        disabled={sending || room.status !== "active"}
                      />
                      <button type="submit" className="btn-primary shrink-0 px-6" disabled={!answer.trim() || sending || room.status !== "active"}>
                        {sending ? "Checking" : "Strike"}
                        <span className="kbd">Enter</span>
                      </button>
                    </div>
                    <div className="mt-2 min-h-[28px] text-sm">
                      {preview && q.kind !== "recall" && (
                        <span className="text-muted">
                          Reads as <TeX tex={preview} />
                        </span>
                      )}
                    </div>
                    </div>
                    {note && (
                      <p className="text-sm text-xp" role="alert">
                        {note}
                      </p>
                    )}
                  </form>
                </div>
              )}
            </section>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Leaderboard room={room} meId={me.id} />
            <Feed events={room.feed} />
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- pieces

function Lobby({ room, onStart, onLeave }: { room: PartyRoom; onStart: () => void; onLeave: () => void }) {
  const me = room.you!;
  const host = room.players.find((p) => p.is_host);
  const [links, setLinks] = useState<string[]>([]);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    const here = `${location.origin}/party/${room.code}`;
    if (!["localhost", "127.0.0.1", "[::1]"].includes(location.hostname)) {
      setLinks([here]);
      return;
    }
    api
      .partyNetwork()
      .then(({ addresses }) => setLinks(addresses.length ? addresses.map((a) => `${location.protocol}//${a}:${location.port || 80}/party/${room.code}`) : [here]))
      .catch(() => setLinks([here]));
  }, [room.code]);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(text);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      /* select the text by hand */
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <section className="panel p-6" aria-labelledby="code-title">
        <p id="code-title" className="text-sm text-muted">
          Room code
        </p>
        <p className="mt-1 font-display text-6xl font-bold tracking-[0.3em] text-cyan">{room.code}</p>
        <div className="mt-6 space-y-2">
          <p className="text-sm text-muted">Friends on the same Wi-Fi open:</p>
          {links.map((l) => (
            <div key={l} className="flex items-center gap-2 rounded-chip border border-line bg-ink/60 px-3 py-2">
              <code className="min-w-0 flex-1 truncate font-mono text-sm">{l}</code>
              <button type="button" className="shrink-0 text-muted hover:text-text" onClick={() => void copy(l)} aria-label="Copy link">
                {copied === l ? <Check size={16} className="text-heal" /> : <Copy size={16} />}
              </button>
            </div>
          ))}
          <p className="text-xs text-muted">Or they open Reps, go to Party raid, and type the code. If Windows asks, allow Node.js on private networks.</p>
        </div>
      </section>

      <section className="panel flex flex-col p-6" aria-labelledby="party-title">
        <div className="flex items-start gap-4">
          <BossArt courseId={room.course_id} name={room.boss_name} className="h-28 w-28 shrink-0" track />
          <div>
            <h1 id="party-title" className="h-display text-2xl">
              {room.boss_name}
            </h1>
            <p className="text-sm text-muted">{room.course_name}</p>
            <p className="mt-2 text-sm">
              Boss HP will be <span className="font-semibold text-hp">{20 + room.rules.hp_per_player * room.players.length}</span> for {room.players.length}{" "}
              {room.players.length === 1 ? "player" : "players"}. {Math.round(room.duration_s / 60)} minutes on the clock.
            </p>
          </div>
        </div>
        <h2 className="h-display mt-6 text-lg">
          Party <span className="text-sm font-normal text-muted">{room.players.length} of {room.max_players}</span>
        </h2>
        <ul className="mt-2 space-y-1.5">
          {room.players.map((p) => (
            <li key={p.id} className="flex animate-enter items-center gap-2 rounded-chip bg-raised/60 px-3 py-2">
              <span className={`h-2 w-2 rounded-full ${p.connected ? "bg-heal" : "bg-line"}`} title={p.connected ? "Connected" : "Not connected"} />
              <span className="font-medium">{p.name}</span>
              {p.id === me.id && <span className="text-xs text-muted">you</span>}
              {p.is_host && <Crown size={14} className="ml-auto text-xp" aria-label="Host" />}
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted">
          {me.counts ? "Your answers count toward your mastery and XP on this computer." : `You're a guest on ${host?.name ?? "the host"}'s Reps. Your answers count for the leaderboard.`}
        </p>
        <div className="mt-auto flex flex-wrap items-center gap-3 pt-6">
          {me.is_host ? (
            <button type="button" className="btn-primary px-8 py-3" onClick={onStart}>
              <Swords size={18} aria-hidden /> Start the raid
            </button>
          ) : (
            <p className="text-sm text-muted">Waiting for {host?.name ?? "the host"} to start.</p>
          )}
          <button type="button" className="btn-ghost ml-auto" onClick={onLeave}>
            <LogOut size={16} aria-hidden /> Leave
          </button>
        </div>
      </section>
    </div>
  );
}

function Clock({ room, serverNow }: { room: PartyRoom; serverNow: () => number }) {
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    if (!room.ends_at || room.status !== "active") {
      setLeft(null);
      return;
    }
    const tick = () => setLeft(Math.max(0, Math.ceil(room.ends_at! - serverNow())));
    tick();
    const t = setInterval(tick, 250);
    return () => clearInterval(t);
  }, [room.ends_at, room.status, serverNow]);
  if (left === null) return null;
  const urgent = left <= 30;
  return (
    <div className={`flex items-center gap-1.5 font-display text-2xl font-bold tabular-nums ${urgent ? "animate-breathe text-hp" : "text-text"}`} role="timer" aria-label={`${left} seconds left`}>
      <Timer size={20} aria-hidden />
      {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
    </div>
  );
}

function SharedHp({ hp, start }: { hp: number; start: number }) {
  const pct = start ? (hp / start) * 100 : 100;
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="font-display text-sm font-semibold text-hp">Shared boss HP</span>
        <span className="font-display text-2xl font-bold tabular-nums">
          {hp}
          <span className="text-sm font-medium text-muted"> / {start}</span>
        </span>
      </div>
      <div className="relative h-5 w-full overflow-hidden rounded-md bg-ink/80 p-[3px] ring-1 ring-line" role="meter" aria-valuemin={0} aria-valuemax={start} aria-valuenow={hp} aria-label="Boss HP">
        <div className="absolute inset-y-[3px] left-[3px] rounded-[3px] bg-[#FFD27A] transition-[width] delay-[450ms] duration-[650ms] ease-in" style={{ width: `calc(${pct}% - 6px)` }} />
        <div className="relative h-full rounded-[3px] bg-gradient-to-r from-[#FF3D66] to-hp transition-[width] duration-200 ease-out" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Leaderboard({ room, meId }: { room: PartyRoom; meId: string }) {
  const top = Math.max(1, ...room.players.map((p) => p.damage));
  return (
    <section className="panel p-6" aria-labelledby="board-title">
      <h2 id="board-title" className="h-display text-xl">
        Damage
      </h2>
      <ol className="mt-4 space-y-3">
        {room.players.map((p, i) => (
          <li key={p.id} className={p.connected ? "" : "opacity-50"}>
            <div className="flex items-center gap-2 text-sm">
              <span className="w-5 font-display font-bold text-muted">{i + 1}</span>
              <span className={`font-medium ${p.down ? "text-muted line-through" : ""}`}>{p.name}</span>
              {p.id === meId && <span className="text-xs text-muted">you</span>}
              {p.is_host && <Crown size={13} className="text-xp" aria-label="Host" />}
              <span className="ml-auto flex items-center gap-3 tabular-nums">
                <span className="text-muted">
                  {p.correct}/{p.answered}
                </span>
                <span className="flex gap-0.5" aria-label={`${p.hearts} hearts`}>
                  {Array.from({ length: room.max_hearts }, (_, k) => (
                    <span key={k} className={`h-2 w-2 rounded-full ${k < p.hearts ? "bg-hp" : "bg-line"}`} />
                  ))}
                </span>
                <span className="w-10 text-right font-display font-semibold">{p.damage}</span>
              </span>
            </div>
            <div className="ml-7 mt-1 h-1.5 overflow-hidden rounded-full bg-ink ring-1 ring-line">
              <div className="h-full rounded-full bg-sun transition-[width] duration-500" style={{ width: `${(p.damage / top) * 100}%` }} />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

const FEED_ICON: Record<PartyEvent["kind"], { icon: typeof Sword; tone: string }> = {
  hit: { icon: Sword, tone: "text-xp" },
  miss: { icon: X, tone: "text-hp" },
  down: { icon: Skull, tone: "text-hp" },
  revive: { icon: HeartPulse, tone: "text-heal" },
  join: { icon: UserPlus, tone: "text-muted" },
  leave: { icon: LogOut, tone: "text-muted" },
  host: { icon: Crown, tone: "text-xp" },
  start: { icon: Swords, tone: "text-cyan" },
  end: { icon: Flag, tone: "text-cyan" },
  lobby: { icon: RotateCcw, tone: "text-muted" },
};

function Feed({ events }: { events: PartyEvent[] }) {
  return (
    <section className="panel p-6" aria-labelledby="feed-title">
      <h2 id="feed-title" className="h-display text-xl">
        Live feed
      </h2>
      <ul className="mt-4 max-h-[300px] space-y-2 overflow-y-auto pr-1 text-sm" role="log">
        {events.map((e) => {
          const { icon: Icon, tone } = FEED_ICON[e.kind] ?? FEED_ICON.join;
          return (
            <li key={e.id} className="flex animate-enter items-start gap-2">
              <Icon size={15} className={`mt-0.5 shrink-0 ${tone}`} aria-hidden />
              <span>{e.text}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Results({
  room,
  meId,
  counts,
  xp,
  isHost,
  onAgain,
  onLeave,
}: {
  room: PartyRoom;
  meId: string;
  counts: boolean;
  xp: number;
  isHost: boolean;
  onAgain: () => void;
  onLeave: () => void;
}) {
  const title = room.outcome === "victory" ? "Boss down" : room.outcome === "wiped" ? "Party wiped" : "The boss escaped";
  const tone = room.outcome === "victory" ? "text-heal" : room.outcome === "wiped" ? "text-hp" : "text-xp";
  const mvp = room.players[0];
  const answered = room.players.reduce((s, p) => s + p.answered, 0);
  const correct = room.players.reduce((s, p) => s + p.correct, 0);
  return (
    <div className="relative m-auto max-w-md animate-pop text-center">
      {room.outcome === "victory" && <ImpactBurst big count={30} spread={260} color="#5BE3A1" />}
      <p className={`h-display relative text-5xl ${tone}`}>{title}</p>
      <p className="mt-3 text-muted">
        {room.outcome === "victory"
          ? `${room.players.length === 1 ? "You" : "The party"} took ${room.hp_start} HP off ${room.boss_name}.`
          : room.outcome === "wiped"
            ? `Everyone ran out of hearts with ${room.hp} HP left on the boss.`
            : `Time ran out with ${room.hp} of ${room.hp_start} HP left.`}
      </p>
      <p className="mt-6 font-display text-lg">
        {correct} of {answered} correct across the party
      </p>
      {mvp && mvp.damage > 0 && (
        <p className="mt-2 flex items-center justify-center gap-2 text-sm">
          <Crown size={16} className="text-xp" aria-hidden /> Top damage: <span className="font-semibold">{mvp.id === meId ? "you" : mvp.name}</span> with {mvp.damage}
        </p>
      )}
      {counts && xp > 0 && <p className="mt-2 font-display font-semibold text-xp">+{xp} XP this raid</p>}
      <div className="mt-8 flex justify-center gap-3">
        {isHost ? (
          <button type="button" className="btn-primary" onClick={onAgain}>
            <RotateCcw size={16} aria-hidden /> Run it back
          </button>
        ) : (
          <p className="self-center text-sm text-muted">The host can run it back.</p>
        )}
        <button type="button" className="btn-ghost" onClick={onLeave}>
          Leave
        </button>
      </div>
    </div>
  );
}
