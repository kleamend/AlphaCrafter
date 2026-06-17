"use client";

import { useCallback, useEffect, useState } from "react";

import type { ArtifactsResponse, LogsResponse } from "@/lib/schemas";

const LOGS_REFRESH_INTERVAL_MS = 2_500;

export type UseRunRefreshArgs = {
  sessionId: string | null;
  active: boolean;
};

export type RunRefreshState = {
  logs: LogsResponse | null;
  artifacts: ArtifactsResponse | null;
  refresh: () => Promise<void>;
};

export function useRunRefresh({ sessionId, active }: UseRunRefreshArgs): RunRefreshState {
  const [logs, setLogs] = useState<LogsResponse | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactsResponse | null>(null);

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    try {
      const [logsRes, artifactsRes] = await Promise.all([
        fetch(`/api/logs?sessionId=${encodeURIComponent(sessionId)}`, {
          cache: "no-store",
        }),
        fetch(`/api/artifacts?sessionId=${encodeURIComponent(sessionId)}`, {
          cache: "no-store",
        }),
      ]);
      if (logsRes.ok) setLogs((await logsRes.json()) as LogsResponse);
      if (artifactsRes.ok) {
        setArtifacts((await artifactsRes.json()) as ArtifactsResponse);
      }
    } catch {
      // Quiet failure — periodic refresh should not spam the terminal.
    }
  }, [sessionId]);

  useEffect(() => {
    if (!active || !sessionId) return;
    const interval = setInterval(() => {
      void refresh();
    }, LOGS_REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [active, sessionId, refresh]);

  return { logs, artifacts, refresh };
}
