"use client";

import { useCallback, useState } from "react";

import type { AgentPhase } from "@/lib/schemas";

const PHASE_ORDER: ReadonlyArray<AgentPhase> = ["miner", "screener", "trader"];

export type PhaseTracker = {
  activePhase: AgentPhase | null;
  activeCycle: number | null;
  completedAgents: AgentPhase[];
  setActivePhase: (phase: AgentPhase | null) => void;
  setActiveCycle: (cycle: number | null) => void;
  resetPhase: () => void;
};

export function usePhaseTracker(): PhaseTracker {
  const [activePhase, setActivePhaseState] = useState<AgentPhase | null>(null);
  const [activeCycle, setActiveCycleState] = useState<number | null>(null);
  const [completedAgents, setCompletedAgents] = useState<AgentPhase[]>([]);

  const setActivePhase = useCallback((phase: AgentPhase | null) => {
    setActivePhaseState(phase);
    // Anything strictly before the active phase in miner -> screener ->
    // trader order is treated as completed for the current cycle.
    setCompletedAgents(
      phase ? PHASE_ORDER.slice(0, PHASE_ORDER.indexOf(phase)) : []
    );
  }, []);

  const setActiveCycle = useCallback((cycle: number | null) => {
    setActiveCycleState((prev) => {
      if (cycle === null) return null;
      if (prev !== null && cycle > prev) {
        // New cycle: drop accumulated completions so the next cycle starts
        // fresh from the first phase.
        setCompletedAgents([]);
      }
      return cycle;
    });
  }, []);

  const resetPhase = useCallback(() => {
    setActivePhaseState(null);
    setActiveCycleState(null);
    setCompletedAgents([]);
  }, []);

  return {
    activePhase,
    activeCycle,
    completedAgents,
    setActivePhase,
    setActiveCycle,
    resetPhase,
  };
}
