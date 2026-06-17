"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";

import type {
  LogsResponse,
  ParsedAgentActivity,
  ParsedWorkflow,
} from "@/lib/schemas";
import { getCopy, type Locale } from "@/lib/i18n";

import {
  ActivityRows,
  AgentRows,
  WorkflowRows,
} from "./agent-output-rows";
import { buildAgentRows, buildWorkflowRows } from "./agent-output-helpers";

import styles from "./AgentOutputPanel.module.css";

export type AgentOutputPanelProps = {
  workflow: ParsedWorkflow | null;
  agents: LogsResponse["agents"] | null;
  activity: ParsedAgentActivity[];
  searchQuery: string;
  locale?: Locale;
};

type TabId = "workflow" | "activity" | "miner" | "screener" | "trader";

export function AgentOutputPanel({
  workflow,
  agents,
  activity,
  searchQuery,
  locale = "en",
}: AgentOutputPanelProps) {
  const copy = getCopy(locale).output;
  const tabDefs: ReadonlyArray<{ id: TabId; label: string }> = [
    { id: "workflow", label: copy.workflow },
    { id: "activity", label: copy.activity },
    { id: "miner", label: copy.miner },
    { id: "screener", label: copy.screener },
    { id: "trader", label: copy.trader },
  ];
  const [tab, setTab] = useState<TabId>("workflow");
  const [localQuery, setLocalQuery] = useState("");
  const effectiveQuery = (searchQuery || localQuery).trim().toLowerCase();

  const workflowRows = useMemo(() => buildWorkflowRows(workflow), [workflow]);
  const minerRows = useMemo(() => buildAgentRows("miner", agents?.miner), [agents]);
  const screenerRows = useMemo(() => buildAgentRows("screener", agents?.screener), [agents]);
  const traderRows = useMemo(() => buildAgentRows("trader", agents?.trader), [agents]);

  return (
    <section className={styles.panel} aria-label="Agent output panel">
      <header className={styles.header}>
        <h2 className={styles.title}>{copy.title}</h2>
        <p className={styles.hint}>{copy.hint}</p>
      </header>

      <div className={styles.tabsRow}>
        <div className={styles.tabs} role="tablist">
          {tabDefs.map((entry) => (
            <button
              key={entry.id}
              type="button"
              role="tab"
              aria-selected={tab === entry.id}
              className={[styles.tabButton, tab === entry.id ? styles.tabActive : ""].join(" ")}
              onClick={() => setTab(entry.id)}
            >
              {entry.label}
            </button>
          ))}
        </div>
        <label className={styles.searchLabel}>
          <Search size={12} strokeWidth={2} aria-hidden="true" />
          <input
            type="search"
            className={styles.searchInput}
            placeholder={copy.searchRows}
            value={localQuery}
            onChange={(event) => setLocalQuery(event.target.value)}
            aria-label={copy.searchRows}
          />
        </label>
      </div>

      <div className={styles.body} role="tabpanel">
        {tab === "workflow" ? <WorkflowRows rows={workflowRows} query={effectiveQuery} /> : null}
        {tab === "activity" ? <ActivityRows activity={activity} query={effectiveQuery} /> : null}
        {tab === "miner" ? <AgentRows agent="miner" rows={minerRows} query={effectiveQuery} /> : null}
        {tab === "screener" ? (
          <AgentRows agent="screener" rows={screenerRows} query={effectiveQuery} />
        ) : null}
        {tab === "trader" ? (
          <AgentRows agent="trader" rows={traderRows} query={effectiveQuery} />
        ) : null}
      </div>
    </section>
  );
}

export default AgentOutputPanel;
