"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { readErrorMessage, systemLine } from "@/lib/console-helpers";
import type {
  HealthResponse,
  RunStatusResponse,
  SessionSummary,
  TerminalLine,
} from "@/lib/schemas";

export type UseConsoleDataArgs = {
  appendTerminalLine: (line: TerminalLine) => void;
};

export type ConsoleData = {
  sessions: SessionSummary[];
  setSessions: (sessions: SessionSummary[]) => void;
  selectedSessionId: string | null;
  setSelectedSessionId: (id: string | null) => void;
  health: HealthResponse | null;
  healthError: string | null;
  runStatus: RunStatusResponse;
  setRunStatus: (status: RunStatusResponse) => void;
  refreshHealth: () => Promise<void>;
  refreshSessions: () => Promise<void>;
  refreshStatus: () => Promise<void>;
};

const DEFAULT_RUN_STATUS: RunStatusResponse = {
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

export function useConsoleData({ appendTerminalLine }: UseConsoleDataArgs): ConsoleData {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatusResponse>(DEFAULT_RUN_STATUS);

  const refreshHealth = useCallback(async () => {
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      if (!response.ok) {
        setHealthError(await readErrorMessage(response));
        return;
      }
      setHealth((await response.json()) as HealthResponse);
      setHealthError(null);
    } catch (err) {
      setHealthError((err as Error).message || "Failed to load health");
    }
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      const response = await fetch("/api/sessions", { cache: "no-store" });
      if (!response.ok) {
        const msg = await readErrorMessage(response);
        appendTerminalLine(systemLine(`Sessions fetch failed: ${msg}`));
        return;
      }
      const data = (await response.json()) as { sessions: SessionSummary[] };
      setSessions(data.sessions);
      setSelectedSessionId((current) => {
        if (current && data.sessions.some((entry) => entry.id === current)) {
          return current;
        }
        return data.sessions[0]?.id ?? null;
      });
    } catch (err) {
      appendTerminalLine(systemLine(`Sessions fetch error: ${(err as Error).message}`));
    }
  }, [appendTerminalLine]);

  const refreshStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/run/status", { cache: "no-store" });
      if (!response.ok) {
        const msg = await readErrorMessage(response);
        appendTerminalLine(systemLine(`Status fetch failed: ${msg}`));
        return;
      }
      const data = (await response.json()) as RunStatusResponse;
      setRunStatus(data);
    } catch (err) {
      appendTerminalLine(systemLine(`Status fetch error: ${(err as Error).message}`));
    }
  }, [appendTerminalLine]);

  useEffect(() => {
    void refreshHealth();
    void refreshSessions();
    void refreshStatus();
  }, [refreshHealth, refreshSessions, refreshStatus]);

  return useMemo(
    () => ({
      sessions,
      setSessions,
      selectedSessionId,
      setSelectedSessionId,
      health,
      healthError,
      runStatus,
      setRunStatus,
      refreshHealth,
      refreshSessions,
      refreshStatus,
    }),
    [
      sessions,
      selectedSessionId,
      health,
      healthError,
      runStatus,
      refreshHealth,
      refreshSessions,
      refreshStatus,
    ]
  );
}
