"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Activity, TerminalSquare } from "lucide-react";

import { AgentActivityTimeline } from "./AgentActivityTimeline";
import { AgentOutputPanel } from "./AgentOutputPanel";
import { ArtifactBrowser } from "./ArtifactBrowser";
import { LiveTerminal } from "./LiveTerminal";
import { MetricsPanel } from "./MetricsPanel";
import { getCopy, getWorkspaceTabs, type Locale, type WorkspaceTab } from "@/lib/i18n";
import { panelEnter } from "@/lib/motion-system";
import type { ArtifactsResponse, LogsResponse, TerminalLine } from "@/lib/schemas";

import styles from "./ConsoleClient.module.css";

export type WorkspaceProps = {
  locale: Locale;
  workspaceTab: WorkspaceTab;
  onWorkspaceTabChange: (tab: WorkspaceTab) => void;
  activitySearch: string;
  onActivitySearchChange: (query: string) => void;
  logs: LogsResponse | null;
  artifacts: ArtifactsResponse | null;
  terminalLines: TerminalLine[];
  onClearTerminal: () => void;
  emptyMessage: string;
};

function buildPanel(
  tab: WorkspaceTab,
  ctx: {
    logs: LogsResponse | null;
    artifacts: ArtifactsResponse | null;
    activitySearch: string;
    locale: Locale;
    terminalLines: TerminalLine[];
    onClearTerminal: () => void;
    emptyMessage: string;
  },
  copy: ReturnType<typeof getCopy>
) {
  const placeholder = (label: string, ariaLabel: string) => (
    <div className={styles.placeholderPanel} aria-label={ariaLabel}>
      <span className={styles.placeholderLabel}>{label}</span>
      <span>{ctx.emptyMessage}</span>
    </div>
  );

  if (tab === "activity") {
    return ctx.logs
      ? (
          <AgentActivityTimeline
            activity={ctx.logs.activity}
            searchQuery={ctx.activitySearch}
            locale={ctx.locale}
          />
        )
      : placeholder(copy.workspace.activity, "Agent activity placeholder");
  }
  if (tab === "terminal") {
    return (
      <LiveTerminal
        lines={ctx.terminalLines}
        onClear={ctx.onClearTerminal}
        locale={ctx.locale}
      />
    );
  }
  if (tab === "output") {
    return ctx.logs
      ? (
          <AgentOutputPanel
            workflow={ctx.logs.workflow}
            agents={ctx.logs.agents}
            activity={ctx.logs.activity}
            searchQuery={ctx.activitySearch}
            locale={ctx.locale}
          />
        )
      : placeholder(copy.workspace.output, "Agent output panel placeholder");
  }
  if (tab === "artifacts") {
    return <ArtifactBrowser artifacts={ctx.artifacts} locale={ctx.locale} />;
  }
  return ctx.logs
    ? <MetricsPanel snapshots={ctx.logs.snapshots} backtests={ctx.logs.backtests} locale={ctx.locale} />
    : placeholder(copy.workspace.metrics, "Metrics panel placeholder");
}

export function Workspace({
  locale,
  workspaceTab,
  onWorkspaceTabChange,
  activitySearch,
  onActivitySearchChange,
  logs,
  artifacts,
  terminalLines,
  onClearTerminal,
  emptyMessage,
}: WorkspaceProps) {
  const copy = getCopy(locale);
  const workspaceTabs = getWorkspaceTabs(locale);

  const panelCtx = {
    logs,
    artifacts,
    activitySearch,
    locale,
    terminalLines,
    onClearTerminal,
    emptyMessage,
  };
  const mainPanel = buildPanel(workspaceTab, panelCtx, copy);

  // Secondary panel: keep terminal + activity handy at all times.
  const secondaryPanel =
    workspaceTab === "terminal"
      ? (logs
        ? (
            <AgentActivityTimeline
              activity={logs.activity}
              searchQuery={activitySearch}
              locale={locale}
            />
          )
        : (
            <div className={styles.placeholderPanel} aria-label="Agent activity side placeholder">
              <span className={styles.placeholderLabel}>{copy.workspace.activity}</span>
              <span>{emptyMessage}</span>
            </div>
          ))
      : (
          <LiveTerminal
            lines={terminalLines}
            onClear={onClearTerminal}
            locale={locale}
          />
        );

  return (
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
            onChange={(event) => onActivitySearchChange(event.target.value)}
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
            onClick={() => onWorkspaceTabChange(tab.id)}
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
            {mainPanel}
          </motion.div>
        </AnimatePresence>
        <aside className={styles.workspaceAside}>{secondaryPanel}</aside>
      </div>
    </motion.section>
  );
}

export default Workspace;
