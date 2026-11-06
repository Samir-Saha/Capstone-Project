// Runs untrusted JavaScript submissions for the Arena. Mirrors harness.py's "run" mode:
// reads a job as JSON on stdin, calls solve(...args) for every input, prints raw outputs
// after a marker line. Expected outputs never enter this process.
"use strict";

const vm = require("node:vm");
const MARKER = "@@REPS_RESULT@@";

function canon(value) {
  if (value === undefined || value === null) return null;
  if (Array.isArray(value)) return value.map(canon);
  if (value instanceof Set) return [...value].map(canon);
  if (value instanceof Map) return Object.fromEntries([...value].map(([k, v]) => [String(k), canon(v)]));
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "nan";
    if (!Number.isFinite(value)) return value > 0 ? "inf" : "-inf";
    return Number.isInteger(value) ? value : Math.round(value * 1e6) / 1e6;
  }
  if (typeof value === "bigint") return Number(value);
  if (typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) out[String(k)] = canon(v);
    return out;
  }
  return value;
}

function emit(result) {
  process.stdout.write("\n" + MARKER + JSON.stringify(result) + "\n");
}

function describe(err) {
  if (err && err.code === "ERR_SCRIPT_EXECUTION_TIMEOUT") return "Time limit exceeded";
  if (err instanceof RangeError && /call stack/i.test(String(err.message))) return "RangeError: maximum call stack size exceeded";
  return (err && err.name ? err.name : "Error") + ": " + (err && err.message ? err.message : String(err));
}

function main(job) {
  const timeout = Math.max(500, (job.cpu_seconds || 5) * 1000);
  // Nothing from this realm goes in: a host object or function would let code climb out
  // through .constructor.constructor. Builtins come from the context's own realm, and
  // inputs cross as a JSON string (a primitive) parsed inside.
  const context = vm.createContext(Object.create(null), { codeGeneration: { strings: false, wasm: false } });
  vm.runInContext("globalThis.console = { log() {}, error() {}, warn() {}, info() {} };", context);
  let solve;
  try {
    new vm.Script(job.solution, { filename: "solution.js" });
  } catch (err) {
    return { status: "compilation_error", error: describe(err) };
  }
  try {
    solve = vm.runInContext(job.solution + "\n;typeof solve === 'function' ? solve : undefined", context, { timeout });
  } catch (err) {
    return { status: "runtime_error", error: describe(err), outputs: [] };
  }
  if (typeof solve !== "function") return { status: "compilation_error", error: "Define a function named solve." };
  vm.runInContext("globalThis.__run = (json) => solve(...JSON.parse(json));", context);
  const outputs = [];
  const ms = [];
  for (let i = 0; i < job.inputs.length; i++) {
    context.__input = JSON.stringify(job.inputs[i]);
    const t0 = process.hrtime.bigint();
    try {
      const out = vm.runInContext("__run(__input)", context, { timeout });
      ms.push(Number(process.hrtime.bigint() - t0) / 1e6);
      outputs.push(canon(out));
    } catch (err) {
      if (err && err.code === "ERR_SCRIPT_EXECUTION_TIMEOUT") return { status: "time_limit_exceeded", outputs, ms, failed_index: i };
      return { status: "runtime_error", error: describe(err), outputs, ms, failed_index: i };
    }
  }
  return { status: "ok", outputs, ms };
}

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  let result;
  try {
    result = main(JSON.parse(input));
  } catch (err) {
    result = { status: "runtime_error", error: describe(err), outputs: [] };
  }
  emit(result);
});
