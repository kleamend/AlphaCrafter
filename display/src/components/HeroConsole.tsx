"use client";

import { motion } from "framer-motion";

import { AgentCard } from "./AgentCard";
import { FlowMap } from "./FlowMap";
import { StatusRail } from "./StatusRail";
import { heroDeck, panelEnter, terminalLineIn } from "@/lib/motion-system";
import type { AgentPhase } from "@/lib/schemas";

import styles from "./HeroConsole.module.css";

export type HeroConsoleProps = {
  activeAgent: AgentPhase;
  activeToolsByPhase?: Partial<Record<AgentPhase, ReadonlyArray<string>>>;
  className?: string;
};

const PHASE_ORDER: ReadonlyArray<AgentPhase> = ["miner", "screener", "trader"];

export function HeroConsole({ activeAgent, activeToolsByPhase, className }: HeroConsoleProps) {
  const containerClass = [styles.hero, className].filter(Boolean).join(" ");

  return (
    <motion.section
      className={containerClass}
      aria-label="AlphaCrafter hero console"
      variants={heroDeck}
      initial="hidden"
      animate="visible"
    >
      <motion.header className={styles.header} variants={panelEnter}>
        <p className={styles.kicker}>Local control surface</p>
        <h1 className={styles.title}>AlphaCrafter multi-agent console</h1>
        <p className={styles.subtitle}>
          Coordinate the Miner, Screener, and Trader agents through one
          deterministic loop. Status, run controls, and telemetry will live
          below.
        </p>
      </motion.header>

      <div className={styles.body}>
        <motion.div className={styles.flowColumn} variants={panelEnter}>
          <FlowMap activeAgent={activeAgent} />

          <motion.div className={styles.cardsRow} variants={heroDeck}>
            {PHASE_ORDER.map((phase) => (
              <motion.div
                key={phase}
                className={styles.cardSlot}
                variants={panelEnter}
                data-agent-slot={phase}
              >
                <AgentCard
                  agentId={phase}
                  active={activeAgent === phase}
                  activeTools={activeToolsByPhase?.[phase]}
                />
              </motion.div>
            ))}
          </motion.div>
        </motion.div>

        <motion.aside
          className={styles.sidePanel}
          aria-label="Run status and controls"
          variants={panelEnter}
        >
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>Run status</h2>
            <p className={styles.panelHint}>
              Placeholder for the upcoming run controls and live status panel.
            </p>
          </div>
          <StatusRail />
          <div className={styles.placeholderBlock} aria-hidden="true">
            <span className={styles.placeholderLabel}>Run controls</span>
            <span className={styles.placeholderHint}>
              Start / stop, max cycles, and resume will mount here.
            </span>
          </div>
          <motion.div
            className={styles.readyLine}
            variants={terminalLineIn}
            role="status"
            aria-live="polite"
          >
            <span className={styles.readyPrefix}>ready</span>
            <span className={styles.readyText}>
              Awaiting run — boot sequence armed.
            </span>
          </motion.div>
        </motion.aside>
      </div>
    </motion.section>
  );
}

export default HeroConsole;
