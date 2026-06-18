"use client";

import { AnimatePresence, motion } from "framer-motion";
import Image from "next/image";
import { PlayCircle, Radio } from "lucide-react";

import { DemoCyclePlayer } from "./DemoCyclePlayer";
import { FlowMap } from "./FlowMap";
import { RunControlPanel } from "./RunControlPanel";
import { StatusRail } from "./StatusRail";
import {
  getAgentMeta,
  listAgentMeta,
  PHASE_ORDER,
} from "@/lib/agent-meta";
import { extractActiveToolsByPhase } from "@/lib/active-tools";
import { getAgentCopy, getCopy, type ConsoleMode, type Locale } from "@/lib/i18n";
import { buildStatusItems } from "@/lib/status-items";
import { panelEnter } from "@/lib/motion-system";
import type { StatusItem } from "./StatusRail";
import type {
  AgentPhase,
  HealthResponse,
  LogsResponse,
  RunStatusName,
  RunStatusResponse,
  SessionSummary,
} from "@/lib/schemas";

import styles from "./ConsoleClient.module.css";

export type HeroDeckProps = {
  locale: Locale;
  mode: ConsoleMode;
  visualAgent: AgentPhase;
  visualCompletedAgents: AgentPhase[];
  onSpotlightAgent: (agent: AgentPhase) => void;
  logs: LogsResponse | null;
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  maxCycles: number;
  onMaxCyclesChange: (value: number) => void;
  resume: boolean;
  onResumeChange: (value: boolean) => void;
  runStatus: RunStatusName;
  isStarting: boolean;
  isStopping: boolean;
  errorMessage: string | null;
  onStart: () => void;
  onStop: () => void;
  onRefresh: () => void;
  health: HealthResponse | null;
  healthError: string | null;
  activeCycle: number | null;
  terminalLineCount: number;
  onDemoActivePhaseChange: (phase: AgentPhase | null) => void;
  onDemoCompletedAgentsChange: (agents: AgentPhase[]) => void;
  onDemoTerminalLine: (line: import("@/lib/schemas").TerminalLine) => void;
};

export function HeroDeck({
  locale,
  mode,
  visualAgent,
  visualCompletedAgents,
  onSpotlightAgent,
  logs,
  sessions,
  selectedSessionId,
  onSelectSession,
  maxCycles,
  onMaxCyclesChange,
  resume,
  onResumeChange,
  runStatus,
  isStarting,
  isStopping,
  errorMessage,
  onStart,
  onStop,
  onRefresh,
  health,
  healthError,
  activeCycle,
  terminalLineCount,
  onDemoActivePhaseChange,
  onDemoCompletedAgentsChange,
  onDemoTerminalLine,
}: HeroDeckProps) {
  const copy = getCopy(locale);
  const visualMeta = getAgentMeta(visualAgent);
  const visualCopy = getAgentCopy(locale, visualAgent);
  const agentList = listAgentMeta();
  const activeToolsByPhase = extractActiveToolsByPhase(logs, 3);

  const statusItems: StatusItem[] = buildStatusItems({
    health,
    healthError,
    sessions,
    selectedSessionId,
    runStatus: {
      status: runStatus,
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
    } as RunStatusResponse,
    activeCycle,
    terminalLineCount,
    locale,
  });

  return (
    <motion.section
      className={styles.heroDeck}
      aria-label={copy.app.heroLabel}
      variants={panelEnter}
      data-testid="ops-deck"
    >
      <div className={styles.heroIntro}>
        <p className={styles.eyebrow}>{copy.app.eyebrow}</p>
        <h2 className={styles.heroTitle}>{copy.app.title}</h2>
        <p className={styles.heroSubtitle}>{copy.app.subtitle}</p>

        <div className={styles.modeStatement}>
          <span className={styles.modeIcon}>
            {mode === "real" ? <Radio size={16} aria-hidden="true" /> : <PlayCircle size={16} aria-hidden="true" />}
          </span>
          <span>
            <strong>{copy.modes[mode].label}</strong>
            {copy.modes[mode].description}
          </span>
        </div>
      </div>

      <div className={styles.agentTheater} data-agent={visualAgent}>
        <div className={styles.artStack} aria-label={`${visualCopy.role} artwork`}>
          {PHASE_ORDER.map((agentId) => {
            const meta = getAgentMeta(agentId);
            const isActive = visualAgent === agentId;
            return (
              <Image
                key={agentId}
                src={meta.artwork.src}
                alt={getAgentCopy(locale, agentId).role}
                width={meta.artwork.width}
                height={meta.artwork.height}
                priority={isActive}
                className={[
                  styles.agentArtwork,
                  styles[`artwork_${agentId}`],
                  isActive ? styles.agentArtworkActive : styles.agentArtworkIdle,
                ].join(" ")}
              />
            );
          })}
          <span className={styles.scanPlate} aria-hidden="true" />
        </div>

        <div className={styles.agentBrief}>
          <span className={styles.agentStage}>{visualCopy.stage}</span>
          <h3>{visualCopy.role}</h3>
          <p>{visualCopy.tagline}</p>
          <ul>
            {visualCopy.responsibilities.map((line: string) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <div className={styles.toolLine} aria-label={`${visualCopy.role} tools`}>
            {visualMeta.tools.map((tool) => (
              <span
                key={tool}
                className={[
                  styles.toolChip,
                  activeToolsByPhase[visualAgent]?.includes(tool) ? styles.toolChipHot : "",
                ].join(" ")}
              >
                {tool}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.agentSelector} aria-label="Agent selector">
        {agentList.map((agent) => {
          const agentCopy = getAgentCopy(locale, agent.id);
          const isActive = visualAgent === agent.id;
          return (
            <button
              key={agent.id}
              type="button"
              className={[
                styles.agentButton,
                styles[`agentButton_${agent.id}`],
                isActive ? styles.agentButtonActive : "",
              ].join(" ")}
              onClick={() => onSpotlightAgent(agent.id)}
              aria-current={isActive ? "step" : undefined}
            >
              <Image
                src={agent.icon.src}
                alt={agent.icon.alt}
                width={agent.icon.width}
                height={agent.icon.height}
                className={styles.agentButtonImage}
              />
              <span>
                <span className={styles.agentButtonStage}>{agentCopy.stage}</span>
                <span className={styles.agentButtonRole}>{agentCopy.role}</span>
              </span>
            </button>
          );
        })}
      </div>

      <aside className={styles.commandDock}>
        <AnimatePresence mode="wait">
          {mode === "real" ? (
            <motion.div
              key="real-run"
              variants={panelEnter}
              initial="hidden"
              animate="visible"
              exit={{ opacity: 0, y: -8 }}
            >
              <RunControlPanel
                sessions={sessions}
                selectedSessionId={selectedSessionId}
                onSelectSession={onSelectSession}
                maxCycles={maxCycles}
                onMaxCyclesChange={onMaxCyclesChange}
                resume={resume}
                onResumeChange={onResumeChange}
                runStatus={runStatus}
                isStarting={isStarting}
                isStopping={isStopping}
                errorMessage={errorMessage}
                onStart={onStart}
                onStop={onStop}
                onRefresh={onRefresh}
                locale={locale}
              />
            </motion.div>
          ) : (
            <motion.div
              key="guided-demo"
              variants={panelEnter}
              initial="hidden"
              animate="visible"
              exit={{ opacity: 0, y: -8 }}
            >
              <DemoCyclePlayer
                locale={locale}
                onActivePhaseChange={onDemoActivePhaseChange}
                onCompletedAgentsChange={onDemoCompletedAgentsChange}
                onTerminalLine={onDemoTerminalLine}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </aside>

      <div className={styles.flowDeck}>
        <div className={styles.flowHeader}>
          <span className={styles.flowKicker}>{copy.flow.title}</span>
          <strong>{copy.flow.subtitle}</strong>
        </div>
        <FlowMap
          activeAgent={visualAgent}
          completedAgents={visualCompletedAgents}
          locale={locale}
        />
        <StatusRail items={statusItems} ariaLabel={copy.status.systemStatus} />
      </div>
    </motion.section>
  );
}

export default HeroDeck;
