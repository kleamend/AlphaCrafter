"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play, RotateCcw, SkipForward } from "lucide-react";

import { AgentCard } from "./AgentCard";
import { PHASE_ORDER } from "@/lib/agent-meta";
import { buildId } from "@/lib/console-helpers";
import { demoSteps, type DemoStep } from "@/lib/demo-data";
import { getCopy, getAgentCopy, type Locale } from "@/lib/i18n";
import { agentDock, panelEnter, terminalLineIn } from "@/lib/motion-system";
import type { AgentPhase, TerminalLine } from "@/lib/schemas";

import styles from "./DemoCyclePlayer.module.css";

const LOG_RING_LIMIT = 200;

type DemoEventLine = { id: string; text: string; at: string };

function appendLog(prev: DemoEventLine[], next: DemoEventLine): DemoEventLine[] {
  if (prev.length < LOG_RING_LIMIT) return [...prev, next];
  return [...prev.slice(prev.length - LOG_RING_LIMIT + 1), next];
}

function completedAgentsFor(phase: AgentPhase): AgentPhase[] {
  return PHASE_ORDER.slice(0, PHASE_ORDER.indexOf(phase));
}

function formatTime(at: string): string {
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return at;
  return [
    date.getHours().toString().padStart(2, "0"),
    date.getMinutes().toString().padStart(2, "0"),
    date.getSeconds().toString().padStart(2, "0"),
  ].join(":");
}

export type DemoCyclePlayerProps = {
  onActivePhaseChange?: (phase: AgentPhase | null) => void;
  onCompletedAgentsChange?: (agents: AgentPhase[]) => void;
  onTerminalLine?: (line: TerminalLine) => void;
  autoAdvanceMs?: number;
  className?: string;
  locale?: Locale;
};

export function DemoCyclePlayer({
  onActivePhaseChange,
  onCompletedAgentsChange,
  onTerminalLine,
  autoAdvanceMs = 2500,
  className,
  locale = "en",
}: DemoCyclePlayerProps) {
  const copy = getCopy(locale).demo;
  const [stepIndex, setStepIndex] = useState<number>(-1);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentStep, setCurrentStep] = useState<DemoStep | null>(null);
  const [log, setLog] = useState<DemoEventLine[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const recordLog = useCallback(
    (text: string) => {
      const at = new Date().toISOString();
      const line: DemoEventLine = { id: buildId(), text, at };
      setLog((prev) => appendLog(prev, line));
      onTerminalLine?.({
        id: line.id,
        stream: "system",
        text: `[demo] ${text}`,
        at,
      });
    },
    [onTerminalLine]
  );

  const applyStep = useCallback(
    (index: number) => {
      if (index < 0 || index >= demoSteps.length) {
        setCurrentStep(null);
        onActivePhaseChange?.(null);
        onCompletedAgentsChange?.([]);
        return;
      }
      const step = demoSteps[index];
      setCurrentStep(step);
      onActivePhaseChange?.(step.phase);
      onCompletedAgentsChange?.(completedAgentsFor(step.phase));
      recordLog(`${step.phase} -> ${step.title}: ${step.detail}`);
    },
    [onActivePhaseChange, onCompletedAgentsChange, recordLog]
  );

  const advance = useCallback(() => {
    setStepIndex((prev) => {
      const next = prev + 1;
      if (next >= demoSteps.length) {
        setIsPlaying(false);
        applyStep(demoSteps.length - 1);
        return prev;
      }
      applyStep(next);
      return next;
    });
  }, [applyStep]);

  const handlePlayPause = useCallback(() => {
    if (isPlaying) {
      setIsPlaying(false);
      clearTimer();
      return;
    }
    if (demoSteps.length === 0) return;
    if (stepIndex >= demoSteps.length - 1) {
      setStepIndex(-1);
      setLog([]);
      recordLog(copy.restarted);
    }
    setIsPlaying(true);
    if (stepIndex === -1) advance();
  }, [advance, clearTimer, copy.restarted, isPlaying, recordLog, stepIndex]);

  const handleReset = useCallback(() => {
    setIsPlaying(false);
    clearTimer();
    setStepIndex(-1);
    setCurrentStep(null);
    setLog([]);
    onActivePhaseChange?.(null);
    onCompletedAgentsChange?.([]);
    recordLog(copy.resetLog);
  }, [clearTimer, copy.resetLog, onActivePhaseChange, onCompletedAgentsChange, recordLog]);

  const handleStepForward = useCallback(() => {
    setIsPlaying(false);
    clearTimer();
    setStepIndex((prev) => {
      const next = prev + 1;
      if (next >= demoSteps.length) return prev;
      applyStep(next);
      return next;
    });
  }, [applyStep, clearTimer]);

  useEffect(() => {
    if (!isPlaying) return;
    timerRef.current = setTimeout(() => advance(), autoAdvanceMs);
    return clearTimer;
  }, [advance, autoAdvanceMs, clearTimer, isPlaying, stepIndex]);

  useEffect(() => clearTimer, [clearTimer]);

  useEffect(() => {
    recordLog(copy.sessionStarted);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const atEnd = stepIndex >= demoSteps.length - 1;
  const containerClass = [styles.player, className].filter(Boolean).join(" ");

  return (
    <section className={containerClass} aria-label="Guided demo cycle player" data-testid="demo-cycle-player">
      <header className={styles.header}>
        <div className={styles.headerRow}>
          <span className={styles.modeBadge} aria-label="Mode">{copy.mode}</span>
          <span className={styles.stepCounter}>
            {locale === "zh" ? "步骤" : "Step"} {Math.max(stepIndex + 1, 0)} / {demoSteps.length}
          </span>
        </div>
        <h2 className={styles.title}>{copy.title}</h2>
        <p className={styles.notice}>{copy.notice}</p>
      </header>

      <div className={styles.controls} role="group" aria-label="Demo controls">
        <button type="button" className={[styles.button, styles.primaryButton].join(" ")} onClick={handlePlayPause} aria-pressed={isPlaying}>
          {isPlaying ? <Pause size={14} strokeWidth={2} aria-hidden="true" /> : <Play size={14} strokeWidth={2} aria-hidden="true" />}
          {isPlaying ? copy.pause : copy.play}
        </button>
        <button type="button" className={styles.button} onClick={handleStepForward} disabled={atEnd}>
          <SkipForward size={14} strokeWidth={2} aria-hidden="true" /> {copy.step}
        </button>
        <button type="button" className={styles.button} onClick={handleReset}>
          <RotateCcw size={14} strokeWidth={2} aria-hidden="true" /> {copy.reset}
        </button>
      </div>

      <div className={styles.cardsRow} aria-label="Demo agent cards">
        {PHASE_ORDER.map((phase) => {
          const active = currentStep?.phase === phase;
          return (
            <motion.div key={phase} className={[styles.cardSlot, active ? styles.cardActive : styles.cardIdle].join(" ")} variants={agentDock} animate={active ? "active" : "idle"}>
                <AgentCard agentId={phase} active={active} compact locale={locale} />
            </motion.div>
          );
        })}
      </div>

      <div className={styles.handoffAndLog}>
        <aside className={styles.handoff} aria-label={copy.currentHandoff} aria-live="polite">
          <span className={styles.handoffLabel}>{copy.currentHandoff}</span>
          <AnimatePresence mode="wait">
            {currentStep ? (
              <motion.div
                key={`${currentStep.phase}-${stepIndex}`}
                className={styles.handoffBody}
                variants={panelEnter}
                initial="hidden"
                animate="visible"
                exit={{ opacity: 0, y: -6 }}
              >
                <span className={styles.handoffTitle}>{currentStep.title}</span>
                <span className={styles.handoffDetail}>{currentStep.detail}</span>
                <span className={styles.handoffMeta}>{getAgentCopy(locale, currentStep.phase).role} {copy.handoff}</span>
              </motion.div>
            ) : (
              <motion.span
                key="handoff-empty"
                className={styles.handoffEmpty}
                variants={panelEnter}
                initial="hidden"
                animate="visible"
              >
                {copy.empty}
              </motion.span>
            )}
          </AnimatePresence>
        </aside>
        <div className={styles.terminal} role="log" aria-live="polite" aria-label="Guided demo terminal log">
          <span className={styles.terminalLabel}>{copy.demoLog}</span>
          <div className={styles.terminalBody}>
            {log.length === 0 ? (
              <span className={styles.terminalEmpty}>{copy.noEvents}</span>
            ) : log.map((line) => (
              <motion.div
                key={line.id}
                className={styles.terminalLine}
                variants={terminalLineIn}
                initial="hidden"
                animate="visible"
              >
                <span className={styles.terminalTime}>{formatTime(line.at)}</span>
                <span className={styles.terminalPrefix}>[demo]</span>
                <span className={styles.terminalText}>{line.text}</span>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export default DemoCyclePlayer;
