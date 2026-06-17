import type { AgentPhase, LogsResponse } from "@/lib/schemas";

const PHASE_ORDER: ReadonlyArray<AgentPhase> = ["miner", "screener", "trader"];

// Walk each phase's events in reverse-chronological order and collect unique
// tool names until we hit the cap. The result is consumed by AgentCard to
// trigger the toolCallFlash animation when fresh tool calls land.
export function extractActiveToolsByPhase(
  logs: LogsResponse | null,
  cap: number
): Record<AgentPhase, string[]> {
  const empty: Record<AgentPhase, string[]> = { miner: [], screener: [], trader: [] };
  if (!logs) return empty;
  const result: Record<AgentPhase, string[]> = { miner: [], screener: [], trader: [] };
  for (const phase of PHASE_ORDER) {
    const agent = logs.agents[phase];
    if (!agent) continue;
    const seen = new Set<string>();
    for (let i = agent.events.length - 1; i >= 0 && seen.size < cap; i -= 1) {
      const event = agent.events[i];
      for (const call of event.toolCalls ?? []) {
        if (seen.has(call.name)) continue;
        seen.add(call.name);
        result[phase].push(call.name);
        if (seen.size >= cap) break;
      }
    }
  }
  return result;
}
