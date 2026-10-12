"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PartyResult, PartyRoom, PartySeat } from "./api";

// A seat is per tab (sessionStorage): a reload rejoins, and two tabs can be two players.
const key = (code: string) => `reps.party.${code.toUpperCase()}`;

export function savedSeat(code: string): PartySeat | null {
  try {
    const raw = sessionStorage.getItem(key(code));
    return raw ? (JSON.parse(raw) as PartySeat) : null;
  } catch {
    return null;
  }
}

export function saveSeat(seat: PartySeat) {
  try {
    sessionStorage.setItem(key(seat.code), JSON.stringify(seat));
  } catch {
    /* the seat lasts until this page closes */
  }
}

export function forgetSeat(code: string) {
  try {
    sessionStorage.removeItem(key(code));
  } catch {
    /* nothing saved */
  }
}

/**
 * The socket goes to the same host as the page; Next forwards /api (WebSockets included)
 * to the API. A hosted build whose frontend can't forward sockets sets NEXT_PUBLIC_WS_URL.
 */
function socketUrl(code: string, token: string) {
  const path = `/api/party/${encodeURIComponent(code)}/ws?token=${encodeURIComponent(token)}`;
  const base = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "");
  if (base) return base + path;
  return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}${path}`;
}

type Outgoing = { type: "start" } | { type: "again" } | { type: "leave" } | { type: "answer"; question_id: string; answer: string };

export function useParty(code: string, seat: PartySeat | null) {
  const [room, setRoom] = useState<PartyRoom | null>(null);
  const [link, setLink] = useState<"connecting" | "open" | "retrying">("connecting");
  const [fatal, setFatal] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [result, setResult] = useState<PartyResult | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const skew = useRef(0);

  useEffect(() => {
    if (!seat) return;
    let stopped = false;
    let tries = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const open = () => {
      const sock = new WebSocket(socketUrl(code, seat.token));
      ws.current = sock;
      sock.onopen = () => {
        tries = 0;
        setLink("open");
      };
      sock.onmessage = (ev) => {
        const msg = JSON.parse(String(ev.data)) as { type: string; room?: PartyRoom; message?: string; fatal?: boolean };
        if (msg.type === "state" && msg.room) {
          skew.current = msg.room.server_now - Date.now() / 1000;
          setRoom(msg.room);
        } else if (msg.type === "result") {
          setResult(msg as unknown as PartyResult);
          setNote(null);
        } else if (msg.type === "unparseable" || msg.type === "error") {
          if (msg.fatal) {
            stopped = true;
            setFatal(msg.message ?? "This raid is closed.");
          } else setNote(msg.message ?? null);
        }
      };
      sock.onclose = () => {
        if (stopped) return;
        setLink("retrying");
        tries += 1;
        retry = setTimeout(open, Math.min(8000, 400 * 2 ** tries));
      };
    };
    open();
    const ping = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) ws.current.send('{"type":"ping"}');
    }, 25000);
    return () => {
      stopped = true;
      clearTimeout(retry);
      clearInterval(ping);
      ws.current?.close();
    };
  }, [code, seat]);

  const send = useCallback((msg: Outgoing) => {
    if (ws.current?.readyState !== WebSocket.OPEN) return false;
    ws.current.send(JSON.stringify(msg));
    return true;
  }, []);

  /** Seconds since the epoch on the server's clock, so every player sees the same countdown. */
  const serverNow = useCallback(() => Date.now() / 1000 + skew.current, []);

  return { room, link, fatal, note, setNote, result, setResult, send, serverNow };
}
