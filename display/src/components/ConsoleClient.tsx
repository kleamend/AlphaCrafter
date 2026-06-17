"use client";

import Image from "next/image";
import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Languages, PlayCircle, Radio, TerminalSquare } from "lucide-react";

import { AgentActivityTimeline } from "./AgentActivityTimeline";
import { AgentOutputPanel } from "./AgentOutputPanel";
import { ArtifactBrowser } from "./ArtifactBrowser";
import { DemoCyclePlayer } from "./DemoCyclePlayer";
import { FlowMap } from "./FlowMap";
import { LiveTerminal } from "./LiveTerminal";
import { MetricsPanel } from "./MetricsPanel";
import { RunControlPanel } from "./RunControlPanel";
import { StatusRail } from "./StatusRail";

import { extractActiveToolsByPhase } from "@/lib/active-tools";
import { getAgentMeta, listAgentMeta } from "@/lib/agent-meta";
import {
  appendRingBuffer,
  readErrorMessage,
  systemLine,
} from "@/lib/console-helpers";
import {
  getAgentCopy,
  getCopy,
  getWorkspaceTabs,
  LOCALE_LABELS,
  type ConsoleMode,
  type Locale,
  type WorkspaceTab,
} from "@/lib/i18n";
import { panelEnter, staggerDeck } from "@/lib/motion-system";
import { buildStatusItems } from "@/lib/status-items";
import { useConsoleData } from "@/lib/use-console-data";
import { usePhaseTracker } from "@/lib/use-phase-tracker";
import { useRunEvents } from "@/lib/use-run-events";
import { useRunRefresh } from "@/lib/use-run-refresh";
import type { AgentPhase, TerminalLine } from "@/lib/schemas";

import styles from "./ConsoleClient.module.css";

const ACTIVE_STATUSES = new Set(["starting", "running", "stopping"]);

function isRunStatusActive(status: string): boolean {
  return ACTIVE_STATUSES.has(status);
}

const AGENT_ORDER: ReadonlyArray<AgentPhase> = ["miner", "screener", "trader"];

export function ConsoleClient() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [mode, setMode] = useState<ConsoleMode>("real");
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("activity");
  const [spotlightAgent, setSpotlightAgent] = useState<AgentPhase>("screener");
  const [demoAgent, setDemoAgent] = useState<AgentPhase | null>(null);
  const [demoCompletedAgents, setDemoCompletedAgents] = useState<AgentPhase[]>([]);
  const [maxCycles, setMaxCycles] = useState<number>(10);
  const [resume, setResume] = useState<boolean>(false);
  const [terminalLines, setTerminalLines] = useState<TerminalLine[]>([]);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activitySearch, setActivitySearch] = useState("");
  const copy = getCopy(locale);

  const phaseTracker = usePhaseTracker();
  const { activePhase, activeCycle, completedAgents, setActivePhase, setActiveCycle, resetPhase } =
    phaseTracker;

  const appendTerminalLine = useCallback((line: TerminalLine) => {
    setTerminalLines((prev) => appendRingBuffer(prev, line));
  }, []);

  const data = useConsoleData({ appendTerminalLine });

  const sessionId = data.runStatus.sessionId ?? data.selectedSessionId;
  const runActive = isRunStatusActive(data.runStatus.status);
  const runRefresh = useRunRefresh({ sessionId, active: runActive });
  const logs = runRefresh.logs;
  const artifacts = runRefresh.artifacts;

  useEffect(() => {
    if (activePhase) setSpotlightAgent(activePhase);
  }, [activePhase]);

  useEffect(() => {
    if (!sessionId) return;
    void runRefresh.refresh();
  }, [sessionId, runRefresh]);

  useRunEvents({
    onStatus: (status) => {
      data.setRunStatus(status);
      if (!isRunStatusActive(status.status)) resetPhase();
    },
    onPhase: (phase, cycle, at) => {
      const tail = cycle !== null ? ` (cycle ${cycle})` : "";
      appendTerminalLine(systemLine(`Phase -> ${phase}${tail}`, at));
    },
    onExit: () => {
      void runRefresh.refresh();
    },
    appendTerminalLine,
    setActivePhase,
    setActiveCycle,
  });

  const handleStart = useCallback(async () => {
    if (!data.selectedSessionId) {
      const message = locale === "zh" ? "启动前请先选择一个会话。" : "Pick a session before starting a run.";
      setErrorMessage(message);
      appendTerminalLine(systemLine(message));
      return;
    }
    setIsStarting(true);
    setErrorMessage(null);
    appendTerminalLine(
      systemLine(
        `Starting run for ${data.selectedSessionId} (maxCycles=${maxCycles}, resume=${resume})`
      )
    );
    try {
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: data.selectedSessionId, maxCycles, resume }),
      });
      if (!response.ok) {
        const msg = await readErrorMessage(response);
        setErrorMessage(msg);
        appendTerminalLine(systemLine(`Start failed: ${msg}`));
        return;
      }
      appendTerminalLine(systemLine("Run accepted by the orchestrator."));
      await data.refreshStatus();
    } catch (err) {
      const msg = (err as Error).message || "Failed to start run";
      setErrorMessage(msg);
      appendTerminalLine(systemLine(`Start error: ${msg}`));
    } finally {
      setIsStarting(false);
    }
  }, [appendTerminalLine, data, locale, maxCycles, resume]);

  const handleStop = useCallback(async () => {
    setIsStopping(true);
    setErrorMessage(null);
    appendTerminalLine(systemLine("Stop requested."));
    try {
      const response = await fetch("/api/run/stop", { method: "POST" });
      if (!response.ok) {
        const msg = await readErrorMessage(response);
        setErrorMessage(msg);
        appendTerminalLine(systemLine(`Stop failed: ${msg}`));
        return;
      }
      const payload = (await response.json()) as { message?: string };
      if (payload.message) appendTerminalLine(systemLine(payload.message));
      await data.refreshStatus();
    } catch (err) {
      const msg = (err as Error).message || "Failed to stop run";
      setErrorMessage(msg);
      appendTerminalLine(systemLine(`Stop error: ${msg}`));
    } finally {
      setIsStopping(false);
    }
  }, [appendTerminalLine, data]);

  const handleRefresh = useCallback(() => {
    void data.refreshHealth();
    void data.refreshSessions();
    void data.refreshStatus();
    void runRefresh.refresh();
    appendTerminalLine(systemLine(locale === "zh"
      ? "已刷新环境、会话、运行状态、日志和产物。"
      : "Refreshed health, sessions, run status, logs, and artifacts."));
  }, [appendTerminalLine, data, locale, runRefresh]);

  const handleClearTerminal = useCallback(() => setTerminalLines([]), []);

  const statusItems = useMemo(
    () =>
      buildStatusItems({
        health: data.health,
        healthError: data.healthError,
        sessions: data.sessions,
        selectedSessionId: data.selectedSessionId,
        runStatus: data.runStatus,
        activeCycle,
        terminalLineCount: terminalLines.length,
        locale,
      }),
    [activeCycle, data, locale, terminalLines.length]
  );

  const sessionLogPath = sessionId ? `sandbox/${sessionId}/logs` : null;
  const emptyMessage = sessionId && sessionLogPath
    ? copy.workspace.noLogs.replace("{session}", sessionId)
    : copy.workspace.selectSession;

  // Pull the most recent tool names per phase so the hero agent cards can
  // flash when new tool calls arrive. Capped at 3 to keep the chip list tidy.
  const activeToolsByPhase = useMemo(
    () => extractActiveToolsByPhase(logs, 3),
    [logs]
  );

  const visualAgent: AgentPhase =
    mode === "demo" ? demoAgent ?? spotlightAgent : activePhase ?? spotlightAgent;
  const visualCompletedAgents =
    mode === "demo" ? demoCompletedAgents : completedAgents;
  const visualMeta = getAgentMeta(visualAgent);
  const visualCopy = getAgentCopy(locale, visualAgent);
  const workspaceTabs = getWorkspaceTabs(locale);
  const agentList = listAgentMeta();
  const errorBanner = data.healthError
    ? `${locale === "zh" ? "环境检查失败" : "Environment health check failed"}: ${data.healthError}`
    : null;

  const placeholder = (label: string, ariaLabel: string) => (
    <div className={styles.placeholderPanel} aria-label={ariaLabel}>
      <span className={styles.placeholderLabel}>{label}</span>
      <span>{emptyMessage}</span>
    </div>
  );

  const workspacePanel = () => {
    if (workspaceTab === "activity") {
      return logs
        ? <AgentActivityTimeline activity={logs.activity} searchQuery={activitySearch} locale={locale} />
        : placeholder(copy.workspace.activity, "Agent activity placeholder");
    }
    if (workspaceTab === "terminal") {
      return <LiveTerminal lines={terminalLines} onClear={handleClearTerminal} locale={locale} />;
    }
    if (workspaceTab === "output") {
      return logs
        ? (
          <AgentOutputPanel
            workflow={logs.workflow}
            agents={logs.agents}
            activity={logs.activity}
            searchQuery={activitySearch}
            locale={locale}
          />
        )
        : placeholder(copy.workspace.output, "Agent output panel placeholder");
    }
    if (workspaceTab === "artifacts") {
      return <ArtifactBrowser artifacts={artifacts} locale={locale} />;
    }
    return logs
      ? <MetricsPanel snapshots={logs.snapshots} backtests={logs.backtests} locale={locale} />
      : placeholder(copy.workspace.metrics, "Metrics panel placeholder");
  };

  const secondaryPanel = workspaceTab === "terminal"
    ? (logs
      ? <AgentActivityTimeline activity={logs.activity} searchQuery={activitySearch} locale={locale} />
      : placeholder(copy.workspace.activity, "Agent activity side placeholder"))
    : <LiveTerminal lines={terminalLines} onClear={handleClearTerminal} locale={locale} />;

  return (
    <motion.div
      className={styles.opsShell}
      variants={staggerDeck}
      initial="hidden"
      animate="visible"
    >
      <motion.header className={styles.topbar} variants={panelEnter}>
        <div className={styles.brandBlock}>
          <span className={styles.brandMark}>AC</span>
          <div>
            <p className={styles.brandLabel}>{copy.topbar.product}</p>
            <h1 className={styles.brandTitle}>{copy.app.title}</h1>
          </div>
        </div>

        <div className={styles.topbarControls}>
          <div className={styles.segmented} role="tablist" aria-label="Console mode">
            {(["real", "demo"] as const).map((entry) => (
              <button
                key={entry}
                type="button"
                role="tab"
                className={[styles.segmentButton, mode === entry ? styles.segmentActive : ""].join(" ")}
                onClick={() => setMode(entry)}
                aria-selected={mode === entry}
              >
                {entry === "real" ? <Radio size={15} aria-hidden="true" /> : <PlayCircle size={15} aria-hidden="true" />}
                {entry === "real" ? copy.topbar.realMode : copy.topbar.demoMode}
              </button>
            ))}
          </div>

          <div className={styles.languageSwitch} aria-label={copy.topbar.language}>
            <Languages size={15} aria-hidden="true" />
            {(["zh", "en"] as const).map((entry) => (
              <button
                key={entry}
                type="button"
                className={[styles.langButton, locale === entry ? styles.langActive : ""].join(" ")}
                onClick={() => setLocale(entry)}
              >
                {LOCALE_LABELS[entry]}
              </button>
            ))}
          </div>
        </div>
      </motion.header>

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
            {AGENT_ORDER.map((agentId) => {
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
              {visualCopy.responsibilities.map((line) => (
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
                onClick={() => setSpotlightAgent(agent.id)}
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
              <motion.div key="real-run" variants={panelEnter} initial="hidden" animate="visible" exit={{ opacity: 0, y: -8 }}>
                <RunControlPanel
                  sessions={data.sessions}
                  selectedSessionId={data.selectedSessionId}
                  onSelectSession={data.setSelectedSessionId}
                  maxCycles={maxCycles}
                  onMaxCyclesChange={setMaxCycles}
                  resume={resume}
                  onResumeChange={setResume}
                  runStatus={data.runStatus.status}
                  isStarting={isStarting}
                  isStopping={isStopping}
                  errorMessage={errorMessage}
                  onStart={handleStart}
                  onStop={handleStop}
                  onRefresh={handleRefresh}
                  locale={locale}
                />
              </motion.div>
            ) : (
              <motion.div key="guided-demo" variants={panelEnter} initial="hidden" animate="visible" exit={{ opacity: 0, y: -8 }}>
                <DemoCyclePlayer
                  locale={locale}
                  onActivePhaseChange={(phase) => {
                    setDemoAgent(phase);
                    if (phase) setSpotlightAgent(phase);
                  }}
                  onCompletedAgentsChange={setDemoCompletedAgents}
                  onTerminalLine={appendTerminalLine}
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

      {errorBanner ? (
        <motion.div
          className={styles.errorBanner}
          role="alert"
          variants={panelEnter}
        >
          {errorBanner}
        </motion.div>
      ) : null}

      <motion.section className={styles.workspace} variants={panelEnter}>
        <header className={styles.workspaceHeader}>
          <div>
            <p className={styles.workspaceKicker}>{copy.app.localEnv}</p>
            <h2 className={styles.workspaceTitle}>{copy.workspace.title}</h2>
            <p className={styles.workspaceSubtitle}>{copy.workspace.subtitle}</p>
          </div>
          <label className={styles.activitySearchWrap}>
            <Activity size={15} aria-hidden="true" />
            <input
              type="search"
              className={styles.activitySearch}
              placeholder={copy.workspace.searchPlaceholder}
              value={activitySearch}
              onChange={(event) => setActivitySearch(event.target.value)}
              aria-label={copy.workspace.searchPlaceholder}
            />
          </label>
        </header>

        <div className={styles.workspaceTabs} role="tablist" aria-label={copy.workspace.title}>
          {workspaceTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={workspaceTab === tab.id}
              className={[styles.workspaceTab, workspaceTab === tab.id ? styles.workspaceTabActive : ""].join(" ")}
              onClick={() => setWorkspaceTab(tab.id)}
            >
              {tab.id === "terminal" ? <TerminalSquare size={15} aria-hidden="true" /> : null}
              {tab.label}
            </button>
          ))}
        </div>

        <div className={styles.workspaceGrid}>
          <AnimatePresence mode="wait">
            <motion.div
              key={workspaceTab}
              className={styles.workspaceMain}
              variants={panelEnter}
              initial="hidden"
              animate="visible"
              exit={{ opacity: 0, y: -8 }}
              role="tabpanel"
            >
              {workspacePanel()}
            </motion.div>
          </AnimatePresence>
          <aside className={styles.workspaceAside}>
            {secondaryPanel}
          </aside>
        </div>
      </motion.section>
    </motion.div>
  );
}

export default ConsoleClient;
