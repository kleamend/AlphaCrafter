"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { readErrorMessage, systemLine } from "@/lib/console-helpers";
import type { TerminalLine } from "@/lib/schemas";

export type UseRunControlArgs = {
  appendTerminalLine: (line: TerminalLine) => void;
  selectedSessionId: string | null;
  maxCycles: number;
  resume: boolean;
  refreshStatus: () => Promise<void>;
  refreshHealth: () => Promise<void>;
  refreshSessions: () => Promise<void>;
  refreshRunLogs: () => Promise<void>;
  locale: "zh" | "en";
};

export type RunControl = {
  isStarting: boolean;
  isStopping: boolean;
  errorMessage: string | null;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  refresh: () => void;
};

const ERROR_AUTO_CLEAR_MS = 5_000;

export function useRunControl({
  appendTerminalLine,
  selectedSessionId,
  maxCycles,
  resume,
  refreshStatus,
  refreshHealth,
  refreshSessions,
  refreshRunLogs,
  locale,
}: UseRunControlArgs): RunControl {
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Hold latest values in refs so the handlers below stay referentially
  // stable even when their inputs change. That keeps the useEffect below
  // from re-subscribing on every locale / maxCycles tweak.
  const latestRef = useRef({
    selectedSessionId,
    maxCycles,
    resume,
    locale,
    appendTerminalLine,
    refreshStatus,
    refreshHealth,
    refreshSessions,
    refreshRunLogs,
  });
  latestRef.current = {
    selectedSessionId,
    maxCycles,
    resume,
    locale,
    appendTerminalLine,
    refreshStatus,
    refreshHealth,
    refreshSessions,
    refreshRunLogs,
  };

  // Auto-clear error message after a short window so old failures don't
  // shadow newer successful actions.
  useEffect(() => {
    if (!errorMessage) return;
    const timer = setTimeout(() => setErrorMessage(null), ERROR_AUTO_CLEAR_MS);
    return () => clearTimeout(timer);
  }, [errorMessage]);

  const start = useCallback(async () => {
    const latest = latestRef.current;
    if (!latest.selectedSessionId) {
      const message = latest.locale === "zh"
        ? "启动前请先选择一个会话。"
        : "Pick a session before starting a run.";
      setErrorMessage(message);
      latest.appendTerminalLine(systemLine(message));
      return;
    }
    setIsStarting(true);
    setErrorMessage(null);
    latest.appendTerminalLine(
      systemLine(
        `Starting run for ${latest.selectedSessionId} (maxCycles=${latest.maxCycles}, resume=${latest.resume})`
      )
    );
    try {
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: latest.selectedSessionId,
          maxCycles: latest.maxCycles,
          resume: latest.resume,
        }),
      });
      if (!response.ok) {
        const msg = await readErrorMessage(response);
        setErrorMessage(msg);
        latest.appendTerminalLine(systemLine(`Start failed: ${msg}`));
        return;
      }
      latest.appendTerminalLine(systemLine("Run accepted by the orchestrator."));
      await latest.refreshStatus();
    } catch (err) {
      const msg = (err as Error).message || "Failed to start run";
      setErrorMessage(msg);
      latest.appendTerminalLine(systemLine(`Start error: ${msg}`));
    } finally {
      setIsStarting(false);
    }
  }, []);

  const stop = useCallback(async () => {
    const latest = latestRef.current;
    setIsStopping(true);
    setErrorMessage(null);
    latest.appendTerminalLine(systemLine("Stop requested."));
    try {
      const response = await fetch("/api/run/stop", { method: "POST" });
      if (!response.ok) {
        const msg = await readErrorMessage(response);
        setErrorMessage(msg);
        latest.appendTerminalLine(systemLine(`Stop failed: ${msg}`));
        return;
      }
      const payload = (await response.json()) as { message?: string };
      if (payload.message) latest.appendTerminalLine(systemLine(payload.message));
      await latest.refreshStatus();
    } catch (err) {
      const msg = (err as Error).message || "Failed to stop run";
      setErrorMessage(msg);
      latest.appendTerminalLine(systemLine(`Stop error: ${msg}`));
    } finally {
      setIsStopping(false);
    }
  }, []);

  const refresh = useCallback(() => {
    const latest = latestRef.current;
    void latest.refreshHealth();
    void latest.refreshSessions();
    void latest.refreshStatus();
    void latest.refreshRunLogs();
    latest.appendTerminalLine(
      systemLine(
        latest.locale === "zh"
          ? "已刷新环境、会话、运行状态、日志和产物。"
          : "Refreshed health, sessions, run status, logs, and artifacts."
      )
    );
  }, []);

  return { isStarting, isStopping, errorMessage, start, stop, refresh };
}
