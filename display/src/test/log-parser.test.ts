import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { readLogsForSession } from "@/lib/log-parser";

const FIXTURES_DIR = path.join(__dirname, "fixtures");

let tmpRoot: string;
let sessionId: string;

async function copyFixture(name: string, dest: string): Promise<void> {
  const src = path.join(FIXTURES_DIR, name);
  await fs.copyFile(src, dest);
}

beforeAll(async () => {
  tmpRoot = await fs.mkdtemp(path.join(os.tmpdir(), "alphacrafter-log-parser-"));
  sessionId = "test_session";
  const sessionDir = path.join(tmpRoot, sessionId);
  const logsDir = path.join(sessionDir, "logs");
  await fs.mkdir(logsDir, { recursive: true });

  await copyFixture("workflow.json", path.join(logsDir, "workflow.json"));
  await copyFixture("miner_agent.json", path.join(logsDir, "miner_agent.json"));
  await copyFixture("screener_agent.json", path.join(logsDir, "screener_agent.json"));
  await copyFixture("trader_agent.json", path.join(logsDir, "trader_agent.json"));
  await copyFixture("snapshot.json", path.join(logsDir, "snapshot.json"));
  await copyFixture("backtest_results.json", path.join(logsDir, "backtest_results.json"));
});

afterAll(async () => {
  if (tmpRoot) {
    await fs.rm(tmpRoot, { recursive: true, force: true });
  }
});

describe("readLogsForSession", () => {
  it("parses workflow with three phases across one cycle", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    expect(result.workflow.phases).toHaveLength(3);
    expect(result.workflow.phases.map((p) => p.phase)).toEqual([
      "miner",
      "screener",
      "trader",
    ]);
    expect(result.workflow.latestCycle).toBe(1);
    expect(result.workflow.latestPhase).toBe("trader");
    for (const phase of result.workflow.phases) {
      expect(phase.cycle).toBe(1);
      expect(phase.success).toBe(true);
      expect(phase.timestamp).not.toBeNull();
    }
  });

  it("parses miner agent_init event without iteration / total_cost", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    const initEvent = result.agents.miner.events.find((e) => e.event === "agent_init");
    expect(initEvent).toBeDefined();
    expect(initEvent?.iteration).toBeNull();
    expect(initEvent?.totalCost).toBeNull();
    expect(initEvent?.success).toBeNull();
  });

  it("parses trader run_complete with success / totals / output_text", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    const completeEvent = result.agents.trader.events.find((e) => e.event === "run_complete");
    expect(completeEvent).toBeDefined();
    expect(completeEvent?.success).toBe(true);
    // final_state.output_text is the run summary; iteration_complete entry carries iteration
    const iterEvent = result.agents.trader.events.find((e) => e.event === "iteration_complete");
    expect(iterEvent).toBeUndefined();
    // run_complete event itself does not store iteration in our schema
    expect(completeEvent?.outputText).toContain("Trader finished");
  });

  it("parses tool_error events and maps severity to error", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    const errActivity = result.activity.find((a) => a.event === "tool_error");
    expect(errActivity).toBeDefined();
    expect(errActivity?.severity).toBe("error");
    expect(errActivity?.error ?? result.agents.trader.events[1].error).toContain("Insufficient data");
    const rawError = result.agents.trader.events.find((e) => e.event === "tool_error");
    expect(rawError?.iteration).toBe(3);
  });

  it("extracts tool field for tool_error events", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    const minerError = result.agents.miner.events.find((e) => e.event === "tool_error");
    expect(minerError).toBeDefined();
    expect(minerError?.tool).toBe("search_factor");
    expect(minerError?.error).toBe("Search backend unavailable");
    expect(minerError?.iteration).toBe(2);
  });

  it("parses interval_summary events", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    const summary = result.agents.screener.events.find((e) => e.event === "interval_summary");
    expect(summary).toBeDefined();
    expect(summary?.iteration).toBe(15);
    expect(summary?.outputText).toContain("5 candidate factors");
  });

  it("extracts summary and toolsExecutedInInterval for interval_summary events", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    const summary = result.agents.screener.events.find((e) => e.event === "interval_summary");
    expect(summary).toBeDefined();
    expect(summary?.summary).toBe("Screener evaluated 5 candidate factors.");
    expect(summary?.toolsExecutedInInterval).toEqual(["get_index_data", "search_factor"]);
  });

  it("extracts total_iterations, total_tool_calls, tools_used for run_complete events", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    const completeEvent = result.agents.trader.events.find((e) => e.event === "run_complete");
    expect(completeEvent).toBeDefined();
    expect(completeEvent?.totalIterations).toBe(10);
    expect(completeEvent?.totalToolCalls).toBe(4);
    expect(completeEvent?.toolsUsed).toEqual(["read_file", "write_file", "backtest"]);
    expect(completeEvent?.success).toBe(true);
  });

  it("parses snapshots with net_assets and position rates", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    expect(result.snapshots.points).toHaveLength(1);
    const point = result.snapshots.points[0];
    expect(point.netAssets).toBe(100000.5);
    expect(point.totalAssets).toBe(110000.0);
    expect(point.availableCash).toBe(50000.25);
    expect(point.marketValue).toBe(60000.0);
    expect(point.grossPositionRate).toBe(0.6);
    expect(point.netPositionRate).toBe(0.5);
    expect(result.snapshots.latest).toEqual(point);
  });

  it("parses backtest metrics (Sharpe, MaxDD, Calmar, Return)", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    const byLabel = new Map(result.backtests.metrics.map((m) => [m.label, m]));
    expect(byLabel.get("Sharpe Ratio")?.value).toBe(1.25);
    expect(byLabel.get("Max Drawdown (%)")?.value).toBe(-3.1);
    expect(byLabel.get("Calmar Ratio")?.value).toBe(3.97);
    expect(byLabel.get("Total Return (%)")?.value).toBe(5.42);
    expect(byLabel.get("Annualized Return (%)")?.value).toBe(12.3);
    expect(result.backtests.latestAt).toBe("2024-06-15T11:00:00");
  });

  it("returns empty data and warning for a missing session, never throwing", async () => {
    const result = await readLogsForSession("does_not_exist", { sandboxRoot: tmpRoot });
    expect(result.workflow.phases).toEqual([]);
    expect(result.agents.miner.events).toEqual([]);
    expect(result.agents.screener.events).toEqual([]);
    expect(result.agents.trader.events).toEqual([]);
    expect(result.activity).toEqual([]);
    expect(result.snapshots.points).toEqual([]);
    expect(result.snapshots.latest).toBeNull();
    expect(result.backtests.metrics).toEqual([]);
    expect(result.warnings.length).toBeGreaterThan(0);
  });

  it("returns a warning (not throws) when a log file contains invalid JSON", async () => {
    const brokenDir = path.join(tmpRoot, "broken_session", "logs");
    await fs.mkdir(brokenDir, { recursive: true });
    await fs.writeFile(path.join(brokenDir, "workflow.json"), "{not json", "utf-8");
    const result = await readLogsForSession("broken_session", { sandboxRoot: tmpRoot });
    expect(result.workflow.phases).toEqual([]);
    expect(result.warnings.some((w) => w.includes("Invalid JSON"))).toBe(true);
  });

  it("sorts activity by timestamp and places timestamp-less entries last", async () => {
    const result = await readLogsForSession(sessionId, { sandboxRoot: tmpRoot });
    const timestamped = result.activity.filter((a) => a.timestamp !== null);
    const timestampLess = result.activity.filter((a) => a.timestamp === null);

    for (let i = 1; i < timestamped.length; i++) {
      const prev = timestamped[i - 1].timestamp ?? "";
      const cur = timestamped[i].timestamp ?? "";
      expect(prev <= cur).toBe(true);
    }

    if (timestamped.length > 0 && timestampLess.length > 0) {
      const firstTsIdx = result.activity.findIndex((a) => a.timestamp !== null);
      const firstNoTsIdx = result.activity.findIndex((a) => a.timestamp === null);
      expect(firstNoTsIdx).toBeGreaterThan(firstTsIdx);
    }
  });
});
