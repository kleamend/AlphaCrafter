"use client";

import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";

import { HeroDeck } from "./HeroDeck";
import { Topbar } from "./Topbar";
import { Workspace } from "./Workspace";
import { isActiveRunStatus } from "@/lib/agent-meta";
import { appendRingBuffer, systemLine } from "@/lib/console-helpers";
import { getCopy, type ConsoleMode, type Locale, type WorkspaceTab } from "@/lib/i18n";
import { panelEnter, staggerDeck } from "@/lib/motion-system";
import { useConsoleData } from "@/lib/use-console-data";
import { usePhaseTracker } from "@/lib/use-phase-tracker";
import { useRunControl } from "@/lib/use-run-control";
import { useRunEvents } from "@/lib/use-run-events";
import { useRunRefresh } from "@/lib/use-run-refresh";
import type { AgentPhase, TerminalLine } from "@/lib/schemas";

import styles from "./ConsoleClient.module.css";

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
  const [activitySearch, setActivitySearch] = useState("");
  const [sseReconnectAttempts, setSseReconnectAttempts] = useState(0);
  const copy = getCopy(locale);

  const phaseTracker = usePhaseTracker();
  const {
    activePhase,
    activeCycle,
    completedAgents,
    setActivePhase,
    setActiveCycle,
    resetPhase,
  } = phaseTracker;

  const appendTerminalLine = useCallback((line: TerminalLine) => {
    setTerminalLines((prev) => appendRingBuffer(prev, line));
  }, []);

  const data = useConsoleData({ appendTerminalLine });

  const sessionId = data.runStatus.sessionId ?? data.selectedSessionId;
  const runActive = isActiveRunStatus(data.runStatus.status);
  const runRefresh = useRunRefresh({ sessionId, active: runActive });
  const logs = runRefresh.logs;
  const artifacts = runRefresh.artifacts;

  // Keep <html lang> in sync with the active locale so screen readers and
  // search engines don't see the stale "en" value from the SSR layout.
  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
    }
  }, [locale]);

  useEffect(() => {
    if (activePhase) setSpotlightAgent(activePhase);
  }, [activePhase]);

  useEffect(() => {
    if (!sessionId) return;
    void runRefresh.refresh();
  }, [sessionId, runRefresh]);

  // Expose SSE connection health on the document so QA tooling / e2e tests
  // can assert "the live event stream is up" without scraping the terminal.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.sseAttempts = String(sseReconnectAttempts);
  }, [sseReconnectAttempts]);

  useRunEvents({
    onStatus: (status) => {
      data.setRunStatus(status);
      if (!isActiveRunStatus(status.status)) resetPhase();
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
    onReconnect: () => setSseReconnectAttempts((n) => n + 1),
  });

  const runControl = useRunControl({
    appendTerminalLine,
    selectedSessionId: data.selectedSessionId,
    maxCycles,
    resume,
    refreshStatus: data.refreshStatus,
    refreshHealth: data.refreshHealth,
    refreshSessions: data.refreshSessions,
    refreshRunLogs: runRefresh.refresh,
    locale,
  });

  const sessionLogPath = sessionId ? `sandbox/${sessionId}/logs` : null;
  const emptyMessage = sessionId && sessionLogPath
    ? copy.workspace.noLogs.replace("{session}", sessionId)
    : copy.workspace.selectSession;

  const visualAgent: AgentPhase =
    mode === "demo" ? demoAgent ?? spotlightAgent : activePhase ?? spotlightAgent;
  const visualCompletedAgents =
    mode === "demo" ? demoCompletedAgents : completedAgents;

  const errorBanner = data.healthError
    ? `${locale === "zh" ? "环境检查失败" : "Environment health check failed"}: ${data.healthError}`
    : null;

  return (
    <motion.div
      className={styles.opsShell}
      variants={staggerDeck}
      initial="hidden"
      animate="visible"
    >
      <Topbar
        locale={locale}
        onLocaleChange={setLocale}
        mode={mode}
        onModeChange={setMode}
      />

      <HeroDeck
        locale={locale}
        mode={mode}
        visualAgent={visualAgent}
        visualCompletedAgents={visualCompletedAgents}
        onSpotlightAgent={setSpotlightAgent}
        logs={logs}
        sessions={data.sessions}
        selectedSessionId={data.selectedSessionId}
        onSelectSession={data.setSelectedSessionId}
        maxCycles={maxCycles}
        onMaxCyclesChange={setMaxCycles}
        resume={resume}
        onResumeChange={setResume}
        runStatus={data.runStatus.status}
        isStarting={runControl.isStarting}
        isStopping={runControl.isStopping}
        errorMessage={runControl.errorMessage}
        onStart={runControl.start}
        onStop={runControl.stop}
        onRefresh={runControl.refresh}
        health={data.health}
        healthError={data.healthError}
        activeCycle={activeCycle}
        terminalLineCount={terminalLines.length}
        onDemoActivePhaseChange={(phase) => {
          setDemoAgent(phase);
          if (phase) setSpotlightAgent(phase);
        }}
        onDemoCompletedAgentsChange={setDemoCompletedAgents}
        onDemoTerminalLine={(line) => appendTerminalLine(line)}
      />

      {errorBanner ? (
        <motion.div
          className={styles.errorBanner}
          role="alert"
          variants={panelEnter}
        >
          {errorBanner}
        </motion.div>
      ) : null}

      <Workspace
        locale={locale}
        workspaceTab={workspaceTab}
        onWorkspaceTabChange={setWorkspaceTab}
        activitySearch={activitySearch}
        onActivitySearchChange={setActivitySearch}
        logs={logs}
        artifacts={artifacts}
        terminalLines={terminalLines}
        onClearTerminal={() => setTerminalLines([])}
        emptyMessage={emptyMessage}
      />
    </motion.div>
  );
}

export default ConsoleClient;
