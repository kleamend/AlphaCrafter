import { EventEmitter } from "node:events";

import type { AgentPhase, RunStatusResponse } from "@/lib/schemas";

export type RunEvent =
  | { type: "status"; status: RunStatusResponse; at: string }
  | { type: "stdout"; line: string; at: string }
  | { type: "stderr"; line: string; at: string }
  | { type: "phase"; phase: AgentPhase; cycle: number | null; at: string }
  | { type: "exit"; exitCode: number | null; signal: string | null; at: string };

export const runEventEmitter = new EventEmitter();
// Allow many concurrent SSE clients without warnings in Node.
runEventEmitter.setMaxListeners(0);

export function emitRunEvent(event: RunEvent): void {
  runEventEmitter.emit("run-event", event);
}

export function onRunEvent(listener: (event: RunEvent) => void): () => void {
  runEventEmitter.on("run-event", listener);
  return () => {
    runEventEmitter.off("run-event", listener);
  };
}

// Line splitter for child_process streams. Buffers partial lines and emits
// complete lines (CR or LF separated). Used by process-manager; re-exported
// here so the process module stays focused on lifecycle.
export function consumeLines(
  stream: NodeJS.ReadableStream | null,
  onLine: (line: string) => void
): { flush: () => void } {
  let remainder = "";
  if (!stream) return { flush: () => {} };
  stream.setEncoding("utf-8");
  stream.on("data", (chunk: string) => {
    const merged = remainder + chunk;
    const parts = merged.split(/\r?\n/);
    remainder = parts.pop() ?? "";
    for (const line of parts) {
      if (line.length > 0) onLine(line);
    }
  });
  return {
    flush: () => {
      if (remainder.length > 0) {
        const tail = remainder;
        remainder = "";
        onLine(tail);
      }
    },
  };
}

// Ring buffer helper. Keeps the most recent `limit` lines.
export class RingBuffer {
  private items: string[] = [];
  constructor(private readonly limit: number) {}
  push(line: string): void {
    if (this.items.length >= this.limit) this.items.shift();
    this.items.push(line);
  }
  get size(): number {
    return this.items.length;
  }
}
