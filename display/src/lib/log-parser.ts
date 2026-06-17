import fs from "node:fs/promises";
import path from "node:path";

import { getSessionRoot } from "@/lib/repo-paths";
import type {
  AgentPhase,
  LogsResponse,
  ParsedAgentActivity,
  ParsedAgentLog,
  ParsedBacktestLog,
  ParsedSnapshotLog,
  ParsedSnapshotPoint,
  ParsedToolCall,
  ParsedWorkflow,
  ParsedWorkflowPhase,
} from "@/lib/schemas";

const PREVIEW_LIMIT = 4000;
const ARGS_PREVIEW_LIMIT = 200;

const KNOWN_EVENTS = {
  run_start: "run_start",
  iteration_complete: "iteration_complete",
  tool_error: "tool_error",
  interval_summary: "interval_summary",
  run_complete: "run_complete",
  run_end: "run_end",
} as const;

type ActivityType = ParsedAgentActivity["event"];

const METRIC_UNITS: Record<string, string | null> = {
  "Sharpe Ratio": null,
  "Calmar Ratio": null,
  "Total Return (%)": "%",
  "Annualized Return (%)": "%",
  "Period Return (%)": "%",
  "Max Drawdown (%)": "%",
  "Average Gross Position Rate (%)": "%",
  "Average Net Position Rate (%)": "%",
};

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readField<T>(
  value: unknown,
  key: string,
  guard: (raw: unknown) => T | null
): T | null {
  if (!isObject(value) || !(key in value)) return null;
  return guard((value as Record<string, unknown>)[key]);
}

const readString = (v: unknown, k: string) =>
  readField<string>(v, k, (x) => (typeof x === "string" ? x : null));

const readNumber = (v: unknown, k: string) =>
  readField<number>(v, k, (x) => (typeof x === "number" && Number.isFinite(x) ? x : null));

const readBool = (v: unknown, k: string) =>
  readField<boolean>(v, k, (x) => (typeof x === "boolean" ? x : null));

function readStringArray(v: unknown, k: string): string[] | undefined {
  if (!isObject(v) || !(k in v)) return undefined;
  const raw = (v as Record<string, unknown>)[k];
  if (!Array.isArray(raw)) return undefined;
  return raw.filter((item): item is string => typeof item === "string");
}

function readToolCalls(value: unknown): ParsedToolCall[] {
  const raw = isObject(value) && Array.isArray(value.tool_calls) ? value.tool_calls : [];
  const out: ParsedToolCall[] = [];
  for (const entry of raw) {
    if (!isObject(entry)) continue;
    const args = entry.arguments;
    let argsPreview = "";
    if (typeof args === "string") {
      argsPreview = args;
    } else if (args !== undefined) {
      try {
        argsPreview = JSON.stringify(args);
      } catch {
        argsPreview = String(args);
      }
    }
    if (argsPreview.length > ARGS_PREVIEW_LIMIT) {
      argsPreview = `${argsPreview.slice(0, ARGS_PREVIEW_LIMIT)}...`;
    }
    out.push({
      name: readString(entry, "name") ?? "unknown",
      argumentsPreview: argsPreview,
      callId: readString(entry, "call_id"),
    });
  }
  return out;
}

function pickEventSuccess(entry: Record<string, unknown>): boolean | null {
  const direct = readBool(entry, "success");
  if (direct !== null) return direct;
  const finalState = entry.final_state;
  return isObject(finalState) ? readBool(finalState, "success") : null;
}

function pickEventOutputText(entry: Record<string, unknown>): string {
  const direct = readString(entry, "output_text") ?? readString(entry, "summary");
  if (direct !== null) return direct;
  const finalState = entry.final_state;
  if (isObject(finalState)) {
    const fromFinal = readString(finalState, "output_text");
    if (fromFinal !== null) return fromFinal;
  }
  return "";
}

function parseAgentLog(entries: unknown[]): ParsedAgentLog {
  const events: ParsedAgentLog["events"] = [];
  for (const entry of entries) {
    if (!isObject(entry)) continue;
    const tool = readString(entry, "tool");
    const summary = readString(entry, "summary");
    const toolsExecutedInInterval = readStringArray(entry, "tools_executed_in_interval");
    const totalIterations = readNumber(entry, "total_iterations");
    const totalToolCalls = readNumber(entry, "total_tool_calls");
    const toolsUsed = readStringArray(entry, "tools_used");
    events.push({
      event: readString(entry, "event") ?? "other",
      timestamp: readString(entry, "timestamp"),
      iteration: readNumber(entry, "iteration"),
      success: pickEventSuccess(entry),
      totalCost: readNumber(entry, "total_cost"),
      toolCalls: readToolCalls(entry),
      error: readString(entry, "error"),
      outputText: pickEventOutputText(entry),
      tool: tool ?? undefined,
      summary: summary ?? undefined,
      toolsExecutedInInterval,
      totalIterations,
      totalToolCalls,
      toolsUsed,
    });
  }
  return { events };
}

function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max)}...`;
}

function titleFor(
  agent: AgentPhase,
  entry: ParsedAgentLog["events"][number],
  type: ActivityType
): string {
  switch (type) {
    case "run_start":
      return `${agent} agent run started`;
    case "iteration_complete":
      return `${agent} iteration ${entry.iteration ?? "?"} complete`;
    case "tool_error":
      return `Tool failed in ${agent}`;
    case "interval_summary":
      return `${agent} interval summary (iter ${entry.iteration ?? "?"})`;
    case "run_complete":
      return entry.success === false ? `${agent} run failed` : `${agent} run complete`;
    case "run_end":
      return `${agent} run ended`;
    default:
      return `${agent} ${entry.event}`;
  }
}

function detailFor(
  entry: ParsedAgentLog["events"][number],
  type: ActivityType
): string {
  if (type === "iteration_complete") {
    const tools = entry.toolCalls.map((tc) => `${tc.name}(${tc.argumentsPreview})`).join(", ");
    const cost = entry.totalCost !== null ? `cost $${entry.totalCost.toFixed(4)}` : "";
    return [tools, cost].filter(Boolean).join(" | ");
  }
  if (type === "tool_error") return entry.error ?? "tool error";
  if (type === "run_start" || type === "run_end" || type === "run_complete" || type === "interval_summary") {
    return entry.outputText;
  }
  return entry.outputText || entry.error || entry.event;
}

function severityFor(
  entry: ParsedAgentLog["events"][number],
  type: ActivityType
): ParsedAgentActivity["severity"] {
  if (type === "tool_error") return "error";
  if (type === "run_complete" || type === "run_end") {
    return entry.success === false ? "warning" : type === "run_complete" ? "success" : "info";
  }
  return "info";
}

function buildActivity(agent: AgentPhase, log: ParsedAgentLog): ParsedAgentActivity[] {
  const items: ParsedAgentActivity[] = [];
  for (const entry of log.events) {
    const type: ActivityType = KNOWN_EVENTS[entry.event as keyof typeof KNOWN_EVENTS] ?? "other";
    items.push({
      id: `${agent}-${items.length}-${entry.event}`,
      agent,
      event: type,
      timestamp: entry.timestamp,
      iteration: entry.iteration,
      title: titleFor(agent, entry, type),
      detail: truncate(detailFor(entry, type), PREVIEW_LIMIT),
      toolCalls: entry.toolCalls,
      totalCost: entry.totalCost,
      severity: severityFor(entry, type),
    });
  }
  return items;
}

function sortActivity(items: ParsedAgentActivity[]): ParsedAgentActivity[] {
  return items.slice().sort((a, b) => {
    if (a.timestamp && b.timestamp) return a.timestamp.localeCompare(b.timestamp);
    if (a.timestamp) return -1;
    if (b.timestamp) return 1;
    return a.id.localeCompare(b.id);
  });
}

function readAgentPhase(entry: unknown): AgentPhase | "unknown" {
  const phase = readString(entry, "phase");
  return phase === "miner" || phase === "screener" || phase === "trader" ? phase : "unknown";
}

function parseWorkflow(entries: unknown[]): ParsedWorkflow {
  const phases: ParsedWorkflowPhase[] = [];
  let latestCycle: number | null = null;
  let latestPhase: string | null = null;
  let latestTs: string | null = null;
  for (const entry of entries) {
    if (!isObject(entry)) continue;
    const cycle = readNumber(entry, "cycle");
    const phase = readAgentPhase(entry);
    const ts = readString(entry, "timestamp");
    if (cycle !== null && (latestCycle === null || cycle > latestCycle)) latestCycle = cycle;
    if (ts !== null && (latestTs === null || ts > latestTs)) {
      latestTs = ts;
      latestPhase = phase;
    }
    phases.push({
      cycle,
      phase,
      success: readBool(entry, "success"),
      timestamp: ts,
      outputText: readString(entry, "output_text") ?? "",
    });
  }
  return { phases, latestCycle, latestPhase };
}

function parseSnapshotPoint(entry: unknown): ParsedSnapshotPoint {
  const account = isObject(entry) ? entry.account : null;
  return {
    date: readString(entry, "current_date") ?? readString(entry, "date"),
    netAssets: readNumber(account, "net_assets"),
    totalAssets: readNumber(account, "total_assets"),
    availableCash: readNumber(account, "available_cash"),
    marketValue: readNumber(account, "market_value"),
    grossPositionRate: readNumber(account, "gross_position_rate"),
    netPositionRate: readNumber(account, "net_position_rate"),
  };
}

function parseSnapshots(entries: unknown[]): ParsedSnapshotLog {
  const points = entries.map(parseSnapshotPoint);
  return { points, latest: points.length > 0 ? points[points.length - 1] : null };
}

function parseBacktests(entries: unknown[]): ParsedBacktestLog {
  const metrics: { label: string; value: number | null; unit: string | null }[] = [];
  let latestAt: string | null = null;
  const seen = new Set<string>();
  for (const entry of entries) {
    if (!isObject(entry)) continue;
    const ts = readString(entry, "timestamp");
    if (ts && (latestAt === null || ts > latestAt)) latestAt = ts;
    if (!isObject(entry.metrics)) continue;
    for (const [label, raw] of Object.entries(entry.metrics)) {
      if (seen.has(label)) continue;
      const value = typeof raw === "number" && Number.isFinite(raw) ? raw : null;
      metrics.push({ label, value, unit: METRIC_UNITS[label] ?? null });
      seen.add(label);
    }
  }
  return { metrics, latestAt };
}

type RawRead =
  | { kind: "missing" }
  | { kind: "invalid" }
  | { kind: "error"; message: string }
  | { kind: "ok"; value: unknown };

async function readJsonFile(filePath: string): Promise<RawRead> {
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    try {
      return { kind: "ok", value: JSON.parse(raw) };
    } catch {
      return { kind: "invalid" };
    }
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return { kind: "missing" };
    return { kind: "error", message: (err as Error).message };
  }
}

export type ReadLogsOptions = { sandboxRoot?: string };

export async function readLogsForSession(
  sessionId: string,
  options: ReadLogsOptions = {}
): Promise<LogsResponse> {
  const sessionRoot = options.sandboxRoot
    ? path.join(options.sandboxRoot, sessionId)
    : getSessionRoot(sessionId);
  const logsRoot = path.join(sessionRoot, "logs");
  const warnings: string[] = [];

  const read = async (name: string) => {
    const result = await readJsonFile(path.join(logsRoot, name));
    if (result.kind === "missing") warnings.push(`Missing log file: ${name}`);
    if (result.kind === "invalid") warnings.push(`Invalid JSON in ${name}`);
    if (result.kind === "error") warnings.push(`Failed to read ${name}: ${result.message}`);
    if (result.kind !== "ok") return [];
    if (Array.isArray(result.value)) return result.value;
    if (result.value !== null && result.value !== undefined) return [result.value];
    return [];
  };

  const [workflowRaw, minerRaw, screenerRaw, traderRaw, snapshotRaw, backtestRaw] =
    await Promise.all([
      read("workflow.json"),
      read("miner_agent.json"),
      read("screener_agent.json"),
      read("trader_agent.json"),
      read("snapshot.json"),
      read("backtest_results.json"),
    ]);

  const workflow = parseWorkflow(workflowRaw);
  const miner = parseAgentLog(minerRaw);
  const screener = parseAgentLog(screenerRaw);
  const trader = parseAgentLog(traderRaw);
  const activity = sortActivity([
    ...buildActivity("miner", miner),
    ...buildActivity("screener", screener),
    ...buildActivity("trader", trader),
  ]);

  return {
    workflow,
    agents: { miner, screener, trader },
    activity,
    snapshots: parseSnapshots(snapshotRaw),
    backtests: parseBacktests(backtestRaw),
    warnings,
  };
}

export const __testing = { parseWorkflow, parseAgentLog, parseSnapshots, parseBacktests };
