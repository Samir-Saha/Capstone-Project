"use client";

import { useEffect, useRef, useState } from "react";

/** True when the person has asked the OS for less motion. CSS already shortens
 * animations in that case; this is for motion driven from JavaScript. */
export function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

/** Counts up to `target` once, the first time it's known. */
export function useCountUp(target: number, ms = 900) {
  const reduced = useReducedMotion();
  const [value, setValue] = useState(0);
  const started = useRef(false);
  useEffect(() => {
    if (reduced || started.current) {
      setValue(target);
      return;
    }
    started.current = true;
    const t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / ms);
      setValue(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms, reduced]);
  return value;
}

/** Remembers the previous value of something across renders. */
export function usePrevious<T>(value: T) {
  const ref = useRef<T | undefined>(undefined);
  useEffect(() => {
    ref.current = value;
  }, [value]);
  return ref.current;
}

/** Animates a number from its previous value to the new one (for HP and scores). */
export function useTween(value: number, ms = 600) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (reduced) {
      setShown(value);
      from.current = value;
      return;
    }
    const start = from.current;
    const t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / ms);
      const v = start + (value - start) * (1 - Math.pow(1 - p, 3));
      setShown(Math.round(v));
      from.current = v;
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, ms, reduced]);
  return shown;
}
