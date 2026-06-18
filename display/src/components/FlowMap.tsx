"use client";

import { motion } from "framer-motion";
import { Check } from "lucide-react";

import { PHASE_ORDER, listAgentMeta } from "@/lib/agent-meta";
import { getAgentCopy, getCopy, type Locale } from "@/lib/i18n";
import type { AgentPhase } from "@/lib/schemas";

import styles from "./FlowMap.module.css";

export type FlowMapProps = {
  activeAgent?: AgentPhase | null;
  completedAgents?: ReadonlyArray<AgentPhase>;
  className?: string;
  locale?: Locale;
};

const NODE_X = [12, 50, 88] as const;
const NODE_Y = 50;

function arcPath(
  start: { x: number; y: number },
  end: { x: number; y: number },
  curvature: number
): string {
  const midX = (start.x + end.x) / 2;
  const midY = (start.y + end.y) / 2 - curvature;
  return `M ${start.x} ${start.y} Q ${midX} ${midY} ${end.x} ${end.y}`;
}

function straightPath(
  start: { x: number; y: number },
  end: { x: number; y: number }
): string {
  return `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
}

function beamPath(
  start: { x: number; y: number },
  end: { x: number; y: number }
): string {
  // Curve the data beam slightly downward for visual handoff emphasis.
  const midX = (start.x + end.x) / 2;
  const midY = (start.y + end.y) / 2 + 8;
  return `M ${start.x} ${start.y} Q ${midX} ${midY} ${end.x} ${end.y}`;
}

function beamKey(activeAgent: AgentPhase | null | undefined): string {
  if (!activeAgent) return "beam-idle";
  const idx = PHASE_ORDER.indexOf(activeAgent);
  if (idx < 0) return "beam-idle";
  // Beam points from active agent to the next in line (or back to miner for trader).
  if (activeAgent === "trader") return "beam-trader-miner";
  if (activeAgent === "miner") return "beam-miner-screener";
  if (activeAgent === "screener") return "beam-screener-trader";
  return "beam-idle";
}

export function FlowMap({
  activeAgent = null,
  completedAgents = [],
  className,
  locale = "en",
}: FlowMapProps) {
  const agents = listAgentMeta();
  const copy = getCopy(locale).flow;
  const containerClass = [styles.flowMap, className].filter(Boolean).join(" ");
  const completedSet = new Set<AgentPhase>(completedAgents);

  const nodePositions: Record<AgentPhase, { x: number; y: number }> = {
    miner: { x: NODE_X[0], y: NODE_Y },
    screener: { x: NODE_X[1], y: NODE_Y },
    trader: { x: NODE_X[2], y: NODE_Y },
  };

  const forwardSegments: Array<{
    key: string;
    path: string;
    accent: string;
  }> = [
    {
      key: "edge-miner-screener",
      path: straightPath(nodePositions.miner, nodePositions.screener),
      accent: "var(--miner)",
    },
    {
      key: "edge-screener-trader",
      path: straightPath(nodePositions.screener, nodePositions.trader),
      accent: "var(--screener)",
    },
  ];

  const feedbackPath = arcPath(nodePositions.trader, nodePositions.miner, 36);

  // Beam — a short curved highlight that animates from active node to the
  // next step, keyed by the active phase so framer-motion replays on change.
  const beamSource =
    activeAgent === "miner"
      ? nodePositions.miner
      : activeAgent === "screener"
        ? nodePositions.screener
        : activeAgent === "trader"
          ? nodePositions.trader
          : null;
  const beamTarget =
    activeAgent === "miner"
      ? nodePositions.screener
      : activeAgent === "screener"
        ? nodePositions.trader
        : activeAgent === "trader"
          ? nodePositions.miner
          : null;

  return (
    <div className={containerClass} role="img" aria-label={copy.aria}>
      <svg
        className={styles.svg}
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <marker
            id="flow-arrow-miner"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--miner)" />
          </marker>
          <marker
            id="flow-arrow-screener"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--screener)" />
          </marker>
          <marker
            id="flow-arrow-feedback"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--trader)" />
          </marker>
          <marker
            id="flow-arrow-beam"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--miner-soft)" />
          </marker>
        </defs>

        <line
          x1={nodePositions.miner.x}
          y1={nodePositions.miner.y}
          x2={nodePositions.screener.x}
          y2={nodePositions.screener.y}
          className={styles.railBase}
        />
        <line
          x1={nodePositions.screener.x}
          y1={nodePositions.screener.y}
          x2={nodePositions.trader.x}
          y2={nodePositions.trader.y}
          className={styles.railBase}
        />

        {forwardSegments.map((segment) => (
          <path
            key={segment.key}
            d={segment.path}
            className={styles.forwardEdge}
            stroke={segment.accent}
            markerEnd={`url(#flow-arrow-${segment.key.includes("miner") ? "miner" : "screener"})`}
          />
        ))}

        <path
          d={feedbackPath}
          className={styles.feedbackEdge}
          stroke="var(--trader)"
          markerEnd="url(#flow-arrow-feedback)"
        />

        {beamSource && beamTarget ? (
          <motion.path
            key={beamKey(activeAgent)}
            d={beamPath(beamSource, beamTarget)}
            className={styles.dataBeam}
            stroke="var(--miner-soft)"
            markerEnd="url(#flow-arrow-beam)"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 0.95 }}
            exit={{ pathLength: 0, opacity: 0 }}
            transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
          />
        ) : null}
      </svg>

      <ol className={styles.nodeList}>
        {agents.map((agent) => {
          const agentCopy = getAgentCopy(locale, agent.id);
          const isActive = activeAgent === agent.id;
          const isCompleted = completedSet.has(agent.id);
          const stateClass = isActive
            ? styles.nodeActive
            : isCompleted
              ? styles.nodeCompleted
              : styles.nodeIdle;
          return (
            <li
              key={agent.id}
              className={[
                styles.node,
                styles[`node_${agent.id}`],
                stateClass,
              ]
                .filter(Boolean)
                .join(" ")}
              aria-current={isActive ? "step" : undefined}
            >
              <span className={styles.nodeDot} aria-hidden="true">
                {isCompleted ? (
                  <Check size={10} strokeWidth={3} aria-hidden="true" />
                ) : null}
              </span>
              <span className={styles.nodeLabel}>{agentCopy.shortLabel}</span>
              <span className={styles.nodeRole}>{agentCopy.role}</span>
            </li>
          );
        })}
      </ol>

      <span className={styles.feedbackTag} aria-hidden="true">
        {copy.feedback}
      </span>
    </div>
  );
}

export default FlowMap;
