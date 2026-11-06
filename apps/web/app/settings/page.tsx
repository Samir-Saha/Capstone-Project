"use client";

import { Check, Cpu, Database, FileCode2, ShieldAlert, Sparkles, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, Spinner, Stat } from "@/components/ui";
import { api, notifyProgress, type Health, type Player } from "@/lib/api";
import { setSoundEnabled, soundEnabled } from "@/lib/sound";

const WORK_KEY = "reps.show-work";

function read(key: string) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* kept for this page only */
  }
}

export default function SettingsPage() {
  const [player, setPlayer] = useState<Player | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [name, setName] = useState("");
  const [saved, setSaved] = useState(false);
  const [sound, setSound] = useState(true);
  const [work, setWork] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSound(soundEnabled());
    setWork(read(WORK_KEY) === "on");
    Promise.all([api.player(), api.health()])
      .then(([p, h]) => {
        setPlayer(p);
        setName(p.name);
        setHealth(h);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const saveName = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      setPlayer(await api.rename(name.trim()));
      setSaved(true);
      notifyProgress(0);
      setTimeout(() => setSaved(false), 1600);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  if (error) return <ErrorNote message={error} />;
  if (!player || !health) return <Spinner label="Loading your profile" />;
  const ai = health.integrations.llm;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="h-display text-4xl">Profile and settings</h1>
        <p className="mt-2 text-muted">Everything here is saved on this computer.</p>
      </header>

      <section className="panel p-6" aria-labelledby="profile-title">
        <h2 id="profile-title" className="h-display text-xl">
          Profile
        </h2>
        <form onSubmit={saveName} className="mt-4 flex max-w-md flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label htmlFor="player-name" className="label">
              Name
            </label>
            <input id="player-name" className="field" value={name} maxLength={40} onChange={(e) => setName(e.target.value)} />
          </div>
          <button type="submit" className="btn-primary" disabled={!name.trim() || name.trim() === player.name}>
            {saved ? (
              <>
                <Check size={16} aria-hidden /> Saved
              </>
            ) : (
              "Save"
            )}
          </button>
        </form>
        <div className="mt-6 grid grid-cols-2 gap-6 md:grid-cols-5">
          <Stat value={player.level} label="Level" tone="xp" />
          <Stat value={player.xp.toLocaleString()} label="Total XP" />
          <Stat value={`${player.streak} / ${player.best_streak}`} label="Streak / best" tone="hp" />
          <Stat value={player.stats.questions_answered} label="Questions answered" />
          <Stat value={player.stats.bosses_defeated} label="Bosses defeated" tone="heal" />
        </div>
      </section>

      <section className="panel p-6" aria-labelledby="prefs-title">
        <h2 id="prefs-title" className="h-display text-xl">
          Preferences
        </h2>
        <ul className="mt-4 divide-y divide-line">
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-3">
              <Volume2 size={18} className="text-muted" aria-hidden />
              <span>
                <span className="block font-medium">Sound effects</span>
                <span className="block text-sm text-muted">Hits, misses and victory sounds.</span>
              </span>
            </span>
            <Toggle
              on={sound}
              label="Sound effects"
              onChange={(v) => {
                setSound(v);
                setSoundEnabled(v);
              }}
            />
          </li>
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-3">
              <FileCode2 size={18} className="text-muted" aria-hidden />
              <span>
                <span className="block font-medium">Show your work by default</span>
                <span className="block text-sm text-muted">Start math questions with one-step-per-line answers that get checked line by line.</span>
              </span>
            </span>
            <Toggle
              on={work}
              label="Show your work by default"
              onChange={(v) => {
                setWork(v);
                write(WORK_KEY, v ? "on" : "off");
              }}
            />
          </li>
        </ul>
      </section>

      <section className="panel p-6" aria-labelledby="system-title">
        <h2 id="system-title" className="h-display text-xl">
          How Reps is running
        </h2>
        <ul className="mt-4 space-y-4 text-sm">
          <li className="flex gap-3">
            <Sparkles size={18} className={ai ? "text-heal" : "text-xp"} aria-hidden />
            <span>
              <span className="block font-medium">AI {ai ? `on (${ai.replace("openai:", "")})` : "off"}</span>
              <span className="block text-muted">
                {ai
                  ? "Uploads also get AI-written computational and concept questions, every one checked against your notes or SymPy. Interview reports add STAR scores."
                  : "Uploads still become bosses: questions are built straight from your notes. Add LLM_API_KEY and LLM_MODEL to .env and restart for AI questions and STAR scores."}
              </span>
            </span>
          </li>
          <li className="flex gap-3">
            {health.integrations.code_runner_is_sandbox ? <Cpu size={18} className="text-heal" aria-hidden /> : <ShieldAlert size={18} className="text-xp" aria-hidden />}
            <span>
              <span className="block font-medium">Code runner: {health.integrations.code_runner_is_sandbox ? "Judge0 sandbox" : "this computer (not a sandbox)"}</span>
              <span className="block text-muted">
                {health.integrations.code_runner_is_sandbox
                  ? "Arena code runs in an isolated sandbox."
                  : "Arena code runs here with time and memory limits. That's fine for your own code; a hosted version needs Judge0."}
              </span>
            </span>
          </li>
          <li className="flex gap-3">
            <Database size={18} className="text-cyan" aria-hidden />
            <span>
              <span className="block font-medium">Storage: {health.integrations.supabase ? "Supabase" : "local database"}</span>
              <span className="block text-muted">Progress lives in apps/api/data/reps.db. Deleting that file resets everything.</span>
            </span>
          </li>
        </ul>
      </section>
    </div>
  );
}

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={`relative h-7 w-12 shrink-0 rounded-full transition ${on ? "bg-violet" : "bg-raised ring-1 ring-line"}`}
    >
      <span className={`absolute top-1 h-5 w-5 rounded-full bg-text transition-all ${on ? "left-6" : "left-1"}`} />
    </button>
  );
}
