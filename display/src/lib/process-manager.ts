import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";

import { getAlphaCrafterRoot } from "@/lib/repo-paths";
import type {
  AgentPhase,
  RunStatusName,
  RunStatusResponse,
  StartRunRequest,
} from "@/lib/schemas";
import { assertSafeSessionId, parseMaxCycles } from "@/lib/validators";

import { RingBuffer, consumeLines, emitRunEvent } from "@/lib/run-events";

const STDOUT_LIMIT = 1000;
const STDERR_LIMIT = 500;
const SIGTERM_FALLBACK_MS = 8_000;

const PHASE_PATTERNS: Array<{ phase: AgentPhase; regex: RegExp }> = [
  { phase: "miner", regex: /MINER\s+PHASE/i },
  { phase: "screener", regex: /SCREENER\s+PHASE/i },
  { phase: "trader", regex: /TRADER\s+PHASE/i },
];
const CYCLE_RE = /\bCYCLE\s*[:=]?\s*(\d+)/i;

const IDLE_STATUS: RunStatusResponse = {
  status: "idle",
  runId: null,
  sessionId: null,
  startedAt: null,
  endedAt: null,
  exitCode: null,
  signal: null,
  pid: null,
  stdoutLineCount: 0,
  stderrLineCount: 0,
  lastMessage: null,
};

export type StartRunResult = {
  runId: string;
  status: "starting" | "running";
  sessionId: string;
  commandPreview: string;
  startedAt: string;
};
export type StopRunResult = { ok: boolean; status: "stopping" | "idle"; message: string };
type ActiveRun = {
  runId: string;
  child: ChildProcess;
  sessionId: string;
  startedAt: string;
  pid: number | null;
  stopRequested: boolean;
  sigtermTimer: NodeJS.Timeout | null;
  stdout: RingBuffer;
  stderr: RingBuffer;
  lastMessage: string | null;
  cycle: number | null;
  status: RunStatusName;
  endedAt: string | null;
  exitCode: number | null;
  signal: string | null;
};

export class RunConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RunConflictError";
  }
}

let activeRun: ActiveRun | null = null;

function nowIso(): string {
  return new Date().toISOString();
}

function snapshot(active: ActiveRun | null): RunStatusResponse {
  if (!active) return { ...IDLE_STATUS };
  return {
    status: active.status,
    runId: active.runId,
    sessionId: active.sessionId,
    startedAt: active.startedAt,
    endedAt: active.endedAt,
    exitCode: active.exitCode,
    signal: active.signal,
    pid: active.pid,
    stdoutLineCount: active.stdout.size,
    stderrLineCount: active.stderr.size,
    lastMessage: active.lastMessage,
  };
}

function handleStdoutLine(run: ActiveRun, line: string): void {
  run.stdout.push(line);
  run.lastMessage = line;
  for (const entry of PHASE_PATTERNS) {
    if (entry.regex.test(line)) {
      emitRunEvent({ type: "phase", phase: entry.phase, cycle: run.cycle, at: nowIso() });
      break;
    }
  }
  const m = line.match(CYCLE_RE);
  if (m) {
    const n = Number.parseInt(m[1], 10);
    if (Number.isInteger(n)) run.cycle = n;
  }
}

function sendSignal(signal: NodeJS.Signals): void {
  if (!activeRun?.child.pid) return;
  const pid = activeRun.child.pid;
  try {
    process.kill(-pid, signal);
    return;
  } catch {
    // Process group kill failed; fall through to direct kill.
  }
  try {
    activeRun.child.kill(signal);
  } catch {
    // Process already gone.
  }
}

function clearFallback(run: ActiveRun): void {
  if (run.sigtermTimer) {
    clearTimeout(run.sigtermTimer);
    run.sigtermTimer = null;
  }
}

function finalize(run: ActiveRun): void {
  if (activeRun !== run) return;
  clearFallback(run);
  activeRun = null;
  emitRunEvent({ type: "status", status: snapshot(run), at: nowIso() });
}

export function getRunStatus(): RunStatusResponse {
  return snapshot(activeRun);
}

export async function startRun(input: StartRunRequest): Promise<StartRunResult> {
  const sessionId = assertSafeSessionId(input.sessionId);
  const maxCycles = parseMaxCycles(input.maxCycles);
  const resume = Boolean(input.resume);

  if (activeRun) {
    throw new RunConflictError(
      `Run ${activeRun.runId} is already active (status=${activeRun.status})`
    );
  }

  const runId = randomUUID();
  const startedAt = nowIso();
  const args: string[] = [
    "run", "--no-capture-output", "-n", "ALPHACRAFTER",
    "python", "-u", "main.py",
    sessionId, "--max-cycles", String(maxCycles),
  ];
  if (resume) args.push("--resume");

  const child = spawn("conda", args, {
    cwd: getAlphaCrafterRoot(),
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  const run: ActiveRun = {
    runId,
    child,
    sessionId,
    startedAt,
    pid: child.pid ?? null,
    stopRequested: false,
    sigtermTimer: null,
    stdout: new RingBuffer(STDOUT_LIMIT),
    stderr: new RingBuffer(STDERR_LIMIT),
    lastMessage: null,
    cycle: null,
    status: "starting",
    endedAt: null,
    exitCode: null,
    signal: null,
  };
  activeRun = run;

  child.once("spawn", () => {
    run.status = "running";
    run.pid = child.pid ?? run.pid;
    emitRunEvent({ type: "status", status: snapshot(run), at: nowIso() });
  });

  child.on("error", (err) => {
    run.status = "failed";
    run.endedAt = nowIso();
    run.lastMessage = err.message;
    emitRunEvent({ type: "stderr", line: err.message, at: run.endedAt });
    emitRunEvent({ type: "exit", exitCode: null, signal: null, at: run.endedAt });
    finalize(run);
  });

  child.on("close", (code, signal) => {
    run.endedAt = nowIso();
    run.exitCode = code;
    run.signal = signal;
    if (run.stopRequested) run.status = "stopped";
    else if (code === 0) run.status = "completed";
    else run.status = "failed";
    emitRunEvent({ type: "exit", exitCode: code, signal, at: run.endedAt });
    finalize(run);
  });

  consumeLines(child.stdout, (line) => {
    handleStdoutLine(run, line);
    emitRunEvent({ type: "stdout", line, at: nowIso() });
  });
  consumeLines(child.stderr, (line) => {
    run.stderr.push(line);
    emitRunEvent({ type: "stderr", line, at: nowIso() });
  });

  const tail = `--max-cycles ${maxCycles}${resume ? " --resume" : ""}`;
  const preview = `conda run --no-capture-output -n ALPHACRAFTER python -u main.py ${sessionId} ${tail}`;
  // run.status is "starting" here; the "spawn" listener flips it to "running"
  // once the child has actually launched. The response contract only allows
  // those two values, so the assertion is safe at this point.
  const initialStatus = run.status as "starting" | "running";
  return { runId, status: initialStatus, sessionId, commandPreview: preview, startedAt };
}

export async function stopRun(): Promise<StopRunResult> {
  if (!activeRun) return { ok: true, status: "idle", message: "No active run to stop" };
  if (activeRun.stopRequested) {
    return { ok: true, status: "stopping", message: `Run ${activeRun.runId} is already stopping` };
  }
  activeRun.stopRequested = true;
  activeRun.status = "stopping";
  const runId = activeRun.runId;
  sendSignal("SIGINT");
  activeRun.sigtermTimer = setTimeout(() => {
    if (activeRun && activeRun.runId === runId && !activeRun.endedAt) {
      sendSignal("SIGTERM");
    }
  }, SIGTERM_FALLBACK_MS);
  emitRunEvent({ type: "status", status: snapshot(activeRun), at: nowIso() });
  return {
    ok: true,
    status: "stopping",
    message: `Sent SIGINT to ${runId}; SIGTERM fallback in ${SIGTERM_FALLBACK_MS}ms`,
  };
}
