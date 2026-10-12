"use client";

import katex from "katex";
import { useMemo } from "react";

export function TeX({ tex, display = false, className = "" }: { tex: string; display?: boolean; className?: string }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(tex, { displayMode: display, throwOnError: false, output: "html" });
    } catch {
      return null;
    }
  }, [tex, display]);
  if (!html) return <code className={className}>{tex}</code>;
  return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}
