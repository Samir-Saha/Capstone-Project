"use client";

import { python } from "@codemirror/lang-python";
import { Prec } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { oneDark } from "@codemirror/theme-one-dark";
import CodeMirror from "@uiw/react-codemirror";
import { useMemo, useRef } from "react";

const repsTheme = EditorView.theme(
  {
    "&": { backgroundColor: "#0E1020", color: "#ECEEFF" },
    ".cm-gutters": { backgroundColor: "#0E1020", color: "#4C5280", border: "none" },
    ".cm-activeLine": { backgroundColor: "rgba(139,108,255,0.07)" },
    ".cm-activeLineGutter": { backgroundColor: "rgba(139,108,255,0.12)", color: "#B9A8FF" },
    "&.cm-focused .cm-cursor": { borderLeftColor: "#3FD8E6" },
    "&.cm-focused .cm-selectionBackground, ::selection": { backgroundColor: "rgba(139,108,255,0.35)" },
    ".cm-content": { padding: "12px 0" },
  },
  { dark: true },
);

export function CodeEditor({
  value,
  onChange,
  onRun,
  onSubmit,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  onRun?: () => void;
  onSubmit?: () => void;
  label: string;
}) {
  // Keep the latest callbacks without rebuilding the editor extensions.
  const run = useRef(onRun);
  const submit = useRef(onSubmit);
  run.current = onRun;
  submit.current = onSubmit;

  const extensions = useMemo(
    () => [
      python(),
      repsTheme,
      EditorView.contentAttributes.of({ "aria-label": label }),
      Prec.highest(
        keymap.of([
          { key: "Mod-Enter", run: () => (run.current?.(), true) },
          { key: "Mod-Shift-Enter", run: () => (submit.current?.(), true) },
        ]),
      ),
    ],
    [label],
  );

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      theme={oneDark}
      extensions={extensions}
      height="100%"
      className="h-full"
      basicSetup={{ foldGutter: false, highlightActiveLine: true, autocompletion: true, tabSize: 4 }}
      indentWithTab
    />
  );
}
