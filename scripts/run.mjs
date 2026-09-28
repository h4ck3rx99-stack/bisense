#!/usr/bin/env node
// Cross-platform task runner behind the root `npm run <task>` scripts (works in PowerShell, macOS, Linux).
// Python commands run through `uv` when it is installed, otherwise through server/.venv (pip fallback).
import { spawn, spawnSync } from "node:child_process";
import { copyFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const SERVER = join(ROOT, "server");
const WEB = join(ROOT, "web");
const isWin = process.platform === "win32";
const [task, ...args] = process.argv.slice(2);

const hasUv = spawnSync(isWin ? "where" : "which", ["uv"], { stdio: "ignore" }).status === 0;
const venvPy = join(SERVER, ".venv", isWin ? "Scripts" : "bin", isWin ? "python.exe" : "python");

function py(argv) {
  // argv like ["bisense", "ingest"] or ["uvicorn", ...] or ["pytest", ...]
  if (hasUv) return ["uv", ["run", ...argv]];
  const mod = argv[0] === "bisense" ? "bisense.cli" : argv[0];
  return [venvPy, ["-m", mod, ...argv.slice(1)]];
}

// On Windows, npm/uv are .cmd/.exe shims that need a shell; pass one quoted command string then.
const quote = (a) => (/[\s"&|<>^]/.test(a) ? `"${a.replace(/"/g, '\\"')}"` : a);
function spawnArgs(cmd, cmdArgs) {
  const useShell = isWin && !cmd.endsWith(".exe");
  return useShell ? [[cmd, ...cmdArgs].map(quote).join(" "), [], true] : [cmd, cmdArgs, false];
}

function run(cmd, cmdArgs, opts = {}) {
  const [c, a, shell] = spawnArgs(cmd, cmdArgs);
  const r = spawnSync(c, a, { stdio: "inherit", shell, ...opts, env: { ...process.env, PYTHONIOENCODING: "utf-8", ...(opts.env ?? {}) } });
  if (r.status !== 0) {
    console.error(`\n✗ ${[cmd, ...cmdArgs].join(" ")} failed (exit ${r.status ?? r.signal})`);
    process.exit(r.status ?? 1);
  }
}

const pyRun = (argv, opts = {}) => {
  const [c, a] = py(argv);
  run(c, a, { cwd: SERVER, ...opts });
};
const npmWeb = (script, extra = []) => run("npm", ["run", script, ...(extra.length ? ["--", ...extra] : [])], { cwd: WEB });

function startServer(extraEnv = {}, reload = false) {
  const [c, a] = py(["uvicorn", "bisense.main:app", "--host", process.env.HOST ?? "127.0.0.1", "--port", process.env.PORT ?? "8000", ...(reload ? ["--reload", "--reload-dir", "bisense"] : [])]);
  const [c2, a2, shell] = spawnArgs(c, a);
  return spawn(c2, a2, { cwd: SERVER, stdio: "inherit", shell, env: { ...process.env, PYTHONIOENCODING: "utf-8", ...extraEnv } });
}

const tasks = {
  setup() {
    if (!existsSync(join(ROOT, ".env"))) {
      copyFileSync(join(ROOT, ".env.example"), join(ROOT, ".env"));
      console.log("Created .env from .env.example (add an LLM key there if you have one).");
    }
    if (hasUv) run("uv", ["sync"], { cwd: SERVER });
    else {
      console.log("uv not found: using python -m venv + pip (slower). Install uv from https://docs.astral.sh/uv/ for faster setup.");
      if (!existsSync(venvPy)) run(isWin ? "py" : "python3", isWin ? ["-3.12", "-m", "venv", ".venv"] : ["-m", "venv", ".venv"], { cwd: SERVER });
      run(venvPy, ["-m", "pip", "install", "-e", ".", "pytest", "ruff", "mypy", "types-PyYAML"], { cwd: SERVER });
    }
    run("npm", [existsSync(join(WEB, "package-lock.json")) ? "ci" : "install"], { cwd: WEB });
    pyRun(["bisense", "models"]);
    // Records which dependency set is installed; start-bisense.bat reruns setup when scripts/setup-version.txt changes.
    copyFileSync(join(ROOT, "scripts", "setup-version.txt"), join(ROOT, "data", ".setup-version"));
    console.log("\n✓ Setup done. Next: npm run ingest   then   npm run demo");
  },
  dev() {
    const api = startServer({ APP_ENV: "development" }, true);
    const [wc, wa, wshell] = spawnArgs("npm", ["run", "dev"]);
    const web = spawn(wc, wa, { cwd: WEB, stdio: "inherit", shell: wshell });
    const stop = () => {
      api.kill();
      web.kill();
      process.exit(0);
    };
    process.on("SIGINT", stop);
    process.on("SIGTERM", stop);
    console.log("\nAPI: http://127.0.0.1:8000   Web (hot reload): http://localhost:5173\n");
  },
  ingest: () => pyRun(["bisense", "ingest", ...args]),
  "fetch-public": () => pyRun(["bisense", "fetch-public", ...args]),
  inspect: () => pyRun(["bisense", "inspect", ...args]),
  "search:explain": () => pyRun(["bisense", "search", ...args, "--explain"]),
  eval: () => pyRun(["bisense", "eval", ...args]),
  warm: () => pyRun(["bisense", "warm"]),
  doctor: () => pyRun(["bisense", "doctor"]),
  "gen:types"() {
    pyRun(["bisense", "openapi"]);
    npmWeb("gen:types");
  },
  build: () => npmWeb("build"),
  start() {
    if (!existsSync(join(WEB, "dist", "index.html"))) npmWeb("build");
    startServer({ APP_ENV: "production" });
    console.log(`\nBISense: http://127.0.0.1:${process.env.PORT ?? "8000"}\n`);
  },
  demo() {
    pyRun(["bisense", "doctor"]);
    npmWeb("build");
    startServer({ APP_ENV: "production", DEMO_MODE: "true" });
    console.log(`\n==============================================\n  BISense demo:  http://127.0.0.1:${process.env.PORT ?? "8000"}\n  (Ctrl+C to stop)\n==============================================\n`);
  },
  test() {
    pyRun(["pytest", "-q", ...args], { env: { LLM_PROVIDER: "fake" } });
    npmWeb("test");
  },
  lint() {
    pyRun(["ruff", "check", "bisense", "tests"]);
    pyRun(["ruff", "format", "--check", "bisense", "tests"]);
    npmWeb("lint");
  },
  format() {
    pyRun(["ruff", "format", "bisense", "tests"]);
    pyRun(["ruff", "check", "--fix", "bisense", "tests"]);
  },
  typecheck() {
    pyRun(["mypy"]);
    npmWeb("typecheck");
  },
  e2e: () => npmWeb("e2e", args),
  check() {
    tasks.lint();
    tasks.typecheck();
    tasks.test();
    npmWeb("build");
    pyRun(["bisense", "eval", "--smoke", "--no-llm", "--min-recall", "0.8"]);
    console.log("\n✓ All quality gates passed.");
  },
};

if (!task || !tasks[task]) {
  console.log(`Usage: npm run <task>\nTasks: ${Object.keys(tasks).join(", ")}`);
  process.exit(task ? 1 : 0);
}
tasks[task]();
