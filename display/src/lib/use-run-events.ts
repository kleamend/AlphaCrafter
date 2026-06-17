"use client";

import { useEffect, useRef } from "react";

import { buildId, systemLine } from "@/lib/console-helpers";
import type { AgentPhase, RunStatusResponse, TerminalLine } from "@/lib/schemas";

const ACTIVE_PHASE_STATUSES = new Set<RunStatusResponse["status"]>([
  "starting",
  "running",
  "stopping",
]);

const SSE_ERROR_COOLDOWN_MS = 10_000;

type RunEventPayload =
  | { type: "status"; status: RunStatusResponse; at: string }
  | { type: "stdout"; line: string; at: string }
  | { type: "stderr"; line: string; at: string }
  | { type: "phase"; phase: AgentPhase; cycle: number | null; at: string }
  | { type: "exit"; exitCode: number | null; signal: string | null; at: string };

export type UseRunEventsArgs = {
  onStatus: (status: RunStatusResponse) => void;
  onPhase: (phase: AgentPhase, cycle: number | null, at: string) => void;
  onExit: (exitCode: number | null, signal: string | null, at: string) => void;
  appendTerminalLine: (line: TerminalLine) => void;
  setActivePhase: (phase: AgentPhase | null) => void;
  setActiveCycle: (cycle: number | null) => void;
};

export function useRunEvents({
  onStatus,
  onPhase,
  onExit,
  appendTerminalLine,
  setActivePhase,
  setActiveCycle,
}: UseRunEventsArgs): void {
  const handlersRef = useRef({
    onStatus,
    onPhase,
    onExit,
    appendTerminalLine,
    setActivePhase,
    setActiveCycle,
  });
  handlersRef.current = {
    onStatus,
    onPhase,
    onExit,
    appendTerminalLine,
    setActivePhase,
    setActiveCycle,
  };

  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }
    const source = new EventSource("/api/run/events");
    let lastErrorAt = 0;

    const handleMessage = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as RunEventPayload;
        if (payload.type === "status") {
          handlersRef.current.onStatus(payload.status);
          if (!ACTIVE_PHASE_STATUSES.has(payload.status.status)) {
            handlersRef.current.setActivePhase(null);
            handlersRef.current.setActiveCycle(null);
          }
        } else if (payload.type === "stdout") {
          handlersRef.current.appendTerminalLine({
            id: buildId(),
            stream: "stdout",
            text: payload.line,
            at: payload.at,
          });
        } else if (payload.type === "stderr") {
          handlersRef.current.appendTerminalLine({
            id: buildId(),
            stream: "stderr",
            text: payload.line,
            at: payload.at,
          });
        } else if (payload.type === "phase") {
          handlersRef.current.setActivePhase(payload.phase);
          handlersRef.current.setActiveCycle(payload.cycle);
          handlersRef.current.onPhase(payload.phase, payload.cycle, payload.at);
        } else if (payload.type === "exit") {
          const detail = payload.signal
            ? `signal=${payload.signal}`
            : `code=${payload.exitCode ?? "n/a"}`;
          handlersRef.current.appendTerminalLine(
            systemLine(`Process exited (${detail})`, payload.at)
          );
          handlersRef.current.onExit(payload.exitCode, payload.signal, payload.at);
        }
      } catch {
        // Ignore malformed payloads; SSE will deliver the next event.
      }
    };

    const handleError = () => {
      const now = Date.now();
      if (now - lastErrorAt < SSE_ERROR_COOLDOWN_MS) return;
      lastErrorAt = now;
      handlersRef.current.appendTerminalLine(
        systemLine("SSE connection error — retrying…")
      );
    };

    source.addEventListener("message", handleMessage as EventListener);
    source.addEventListener("error", handleError as EventListener);
    return () => {
      source.removeEventListener("message", handleMessage as EventListener);
      source.removeEventListener("error", handleError as EventListener);
      source.close();
    };
  }, []);
}
