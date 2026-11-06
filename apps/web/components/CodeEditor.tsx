"use client";

import { python } from "@codemirror/lang-python";
import { StreamLanguage } from "@codemirror/language";
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

// A small JavaScript highlighter built on the stream parser that's already installed,
// so adding JavaScript needed no new package.
const JS_KEYWORDS = new Set(
  "break case catch class const continue default delete do else export extends finally for function if in instanceof let new of return switch this throw try typeof var void while yield await async".split(" "),
);
const JS_ATOMS = new Set(["true", "false", "null", "undefined", "NaN", "Infinity"]);
const javascriptLite = StreamLanguage.define<{ comment: boolean }>({
  name: "javascript",
  startState: () => ({ comment: false }),
  token(stream, state) {
    if (state.comment) {
      if (stream.skipTo("*/")) {
        stream.next();
        stream.next();
        state.comment = false;
      } else stream.skipToEnd();
      return "comment";
    }
    if (stream.eatSpace()) return null;
    if (stream.match("//")) {
      stream.skipToEnd();
      return "comment";
    }
    if (stream.match("/*")) {
      state.comment = true;
      return "comment";
    }
    const ch = stream.peek();
    if (ch === '"' || ch === "'" || ch === "`") {
      stream.next();
      let escaped = false;
      for (let c = stream.next(); c != null; c = stream.next()) {
        if (c === ch && !escaped) break;
        escaped = !escaped && c === "\\";
      }
      return "string";
    }
    if (stream.match(/^\d+(\.\d+)?/)) return "number";
    if (stream.match(/^[A-Za-z_$][\w$]*/)) {
      const word = stream.current();
      if (JS_KEYWORDS.has(word)) return "keyword";
      if (JS_ATOMS.has(word)) return "atom";
      return stream.peek() === "(" ? "variableName.function" : "variableName";
    }
    stream.next();
    return "operator";
  },
  languageData: { commentTokens: { line: "//" } },
});

export function CodeEditor({
  value,
  onChange,
  onRun,
  onSubmit,
  label,
  language = "python",
}: {
  language?: "python" | "javascript";
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
      language === "javascript" ? javascriptLite : python(),
      repsTheme,
      EditorView.contentAttributes.of({ "aria-label": label }),
      Prec.highest(
        keymap.of([
          { key: "Mod-Enter", run: () => (run.current?.(), true) },
          { key: "Mod-Shift-Enter", run: () => (submit.current?.(), true) },
        ]),
      ),
    ],
    [label, language],
  );

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      theme={oneDark}
      extensions={extensions}
      height="100%"
      className="h-full"
      basicSetup={{ foldGutter: false, highlightActiveLine: true, autocompletion: true, tabSize: language === "javascript" ? 2 : 4 }}
      indentWithTab
    />
  );
}
