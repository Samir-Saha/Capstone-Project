"use client";

import { Crown, LogIn, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BossArt } from "@/components/BossArt";
import { ErrorNote, Spinner } from "@/components/ui";
import { api, type Course } from "@/lib/api";
import { saveSeat } from "@/lib/party";

const CODE_CHARS = /[^ABCDEFGHJKLMNPQRSTUVWXYZ]/g;

export default function PartyHome() {
  const router = useRouter();
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [courseId, setCourseId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"host" | "join" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [cs, p] = await Promise.all([api.courses(), api.player()]);
        const playable = cs.filter((c) => c.question_types > 0);
        setCourses(playable);
        setCourseId(playable[0]?.id ?? null);
        if (p.name && p.name !== "Player") setName(p.name);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, []);

  const host = async () => {
    if (!courseId || !name.trim()) return;
    setBusy("host");
    setError(null);
    try {
      const seat = await api.partyCreate(courseId, name.trim());
      saveSeat(seat);
      router.push(`/party/${seat.code}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  const join = async () => {
    if (code.length !== 4 || !name.trim()) return;
    setBusy("join");
    setError(null);
    try {
      const seat = await api.partyJoin(code, name.trim());
      saveSeat(seat);
      router.push(`/party/${seat.code}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  return (
    <div className="space-y-8">
      <header>
        <h1 className="h-display flex items-center gap-3 text-4xl">
          <Users size={32} className="text-cyan" aria-hidden /> Party raid
        </h1>
        <p className="mt-2 max-w-2xl text-muted">
          One boss, one HP bar, up to 8 players. Everyone gets their own verified questions, and every correct answer from anyone hits the same boss. Friends on
          your Wi-Fi join with a four-letter code.
        </p>
      </header>

      <div className="max-w-md">
        <label htmlFor="party-name" className="label">
          Your name in the raid
        </label>
        <input id="party-name" className="field" value={name} maxLength={20} onChange={(e) => setName(e.target.value)} placeholder="What should the party call you?" />
      </div>

      {error && <ErrorNote message={error} />}

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <section className="panel p-6" aria-labelledby="host-title">
          <h2 id="host-title" className="h-display flex items-center gap-2 text-xl">
            <Crown size={18} className="text-xp" aria-hidden /> Host a raid
          </h2>
          <p className="mt-1 text-sm text-muted">Pick the boss. You start the raid once everyone's in.</p>
          {!courses ? (
            <div className="mt-6">
              <Spinner label="Loading bosses" />
            </div>
          ) : courses.length === 0 ? (
            <p className="mt-4 text-muted">No courses with verified questions yet.</p>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Boss">
              {courses.map((c) => {
                const on = c.id === courseId;
                return (
                  <button
                    key={c.id}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    onClick={() => setCourseId(c.id)}
                    className={`flex items-center gap-3 rounded-panel border p-3 text-left transition ${on ? "border-violet bg-violet/10" : "border-line hover:border-violet/50"}`}
                  >
                    <BossArt courseId={c.id} name={c.boss_name} className="h-16 w-16 shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-display font-semibold">{c.boss_name}</span>
                      <span className="block truncate text-sm text-muted">{c.name}</span>
                      <span className="block text-xs text-muted">{c.topics.length} topics</span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          <button type="button" className="btn-primary mt-5 w-full py-3 sm:w-auto" onClick={host} disabled={!courseId || !name.trim() || busy !== null}>
            {busy === "host" ? "Opening the room" : "Open a room"}
          </button>
        </section>

        <section className="panel p-6" aria-labelledby="join-title">
          <h2 id="join-title" className="h-display flex items-center gap-2 text-xl">
            <LogIn size={18} className="text-cyan" aria-hidden /> Join a raid
          </h2>
          <p className="mt-1 text-sm text-muted">Get the code from whoever's hosting.</p>
          <form
            className="mt-4"
            onSubmit={(e) => {
              e.preventDefault();
              void join();
            }}
          >
            <label htmlFor="party-code" className="label">
              Room code
            </label>
            <input
              id="party-code"
              className="field text-center font-display text-3xl font-bold uppercase tracking-[0.5em]"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase().replace(CODE_CHARS, "").slice(0, 4))}
              placeholder="ABCD"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              inputMode="text"
            />
            <button type="submit" className="btn-cyan mt-4 w-full py-3" disabled={code.length !== 4 || !name.trim() || busy !== null}>
              {busy === "join" ? "Joining" : "Join"}
            </button>
          </form>
        </section>
      </div>

      <section className="panel p-6" aria-labelledby="rules-title">
        <h2 id="rules-title" className="h-display text-xl">
          How a raid works
        </h2>
        <ul className="mt-3 grid gap-x-8 gap-y-2 text-sm text-muted sm:grid-cols-2">
          <li>The boss starts with 20 HP plus 60 for each player.</li>
          <li>A correct answer deals 8, 11 or 14 damage by difficulty, plus 2 for each answer already in your streak (up to +6).</li>
          <li>Everyone has 3 hearts. A miss costs one, and at zero you're down.</li>
          <li>A 3-answer streak brings back a downed teammate with one heart.</li>
          <li>Six minutes on the clock. Run out of time or teammates and the boss wins.</li>
          <li>The host's answers count toward mastery and XP on this computer. Guests play for the leaderboard.</li>
        </ul>
      </section>
    </div>
  );
}
