import type { TerminalLine } from "@/lib/schemas";

export const TERMINAL_RING_LIMIT = 1000;

export function buildId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

export function systemLine(
  text: string,
  at: string = new Date().toISOString()
): TerminalLine {
  return { id: buildId(), stream: "system", text, at };
}

export function appendRingBuffer(
  prev: TerminalLine[],
  next: TerminalLine
): TerminalLine[] {
  if (prev.length < TERMINAL_RING_LIMIT) return [...prev, next];
  return [...prev.slice(prev.length - TERMINAL_RING_LIMIT + 1), next];
}

export async function readErrorMessage(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { error?: unknown };
    if (data && typeof data.error === "string") return data.error;
  } catch {
    // Non-JSON body, fall through.
  }
  return `Request failed with status ${response.status}`;
}
