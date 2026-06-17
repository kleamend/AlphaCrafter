"use client";

import { motion } from "framer-motion";
import { useMemo } from "react";
import { AlertTriangle, Clock } from "lucide-react";

import { getAgentCopy, getCopy, type Locale } from "@/lib/i18n";
import { terminalLineIn } from "@/lib/motion-system";
import type { AgentPhase, ParsedAgentActivity, ParsedToolCall } from "@/lib/schemas";

import styles from "./AgentActivityTimeline.module.css";

export type AgentActivityTimelineProps = {
  activity: ParsedAgentActivity[];
  searchQuery: string;
  locale?: Locale;
};

const WATCHED_FILES: ReadonlyArray<{ agent: AgentPhase; path: string }> = [
  { agent: "miner", path: "logs/miner_agent.json" },
  { agent: "screener", path: "logs/screener_agent.json" },
  { agent: "trader", path: "logs/trader_agent.json" },
];

function formatTime(at: string | null): string {
  if (!at) return "—";
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return at;
  const hh = date.getHours().toString().padStart(2, "0");
  const mm = date.getMinutes().toString().padStart(2, "0");
  const ss = date.getSeconds().toString().padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function formatCost(value: number | null): string | null {
  if (value === null) return null;
  return `$${value.toFixed(4)}`;
}

function formatToolList(tools: ParsedToolCall[]): string[] {
  return tools.map((tool) => tool.name);
}

function matchesQuery(activity: ParsedAgentActivity, query: string): boolean {
  if (query.length === 0) return true;
  const haystack = [
    activity.title,
    activity.detail,
    activity.agent,
    ...activity.toolCalls.map((tool) => `${tool.name} ${tool.argumentsPreview}`),
  ]
    .join(" \n ")
    .toLowerCase();
  return haystack.includes(query);
}

export function AgentActivityTimeline({
  activity,
  searchQuery,
  locale = "en",
}: AgentActivityTimelineProps) {
  const copy = getCopy(locale).activity;
  const trimmedQuery = searchQuery.trim().toLowerCase();
  const visible = useMemo(
    () => activity.filter((entry) => matchesQuery(entry, trimmedQuery)),
    [activity, trimmedQuery]
  );

  return (
    <section className={styles.panel} aria-label="Agent activity timeline">
      <header className={styles.header}>
        <h2 className={styles.title}>{copy.title}</h2>
        <p className={styles.hint}>{copy.hint}</p>
      </header>

      {activity.length === 0 ? (
        <div className={styles.emptyState}>
          <p className={styles.emptyTitle}>{copy.emptyTitle}</p>
          <p className={styles.emptyBody}>{copy.emptyBody}</p>
          <ul className={styles.watchList}>
            {WATCHED_FILES.map((entry) => {
              const agentCopy = getAgentCopy(locale, entry.agent);
              return (
                <li key={entry.agent} className={styles.watchItem}>
                  <span
                    className={[styles.agentBadge, styles[`agent_${entry.agent}`]].join(" ")}
                  >
                    {agentCopy.shortLabel}
                  </span>
                  <code className={styles.watchPath}>{entry.path}</code>
                </li>
              );
            })}
          </ul>
        </div>
      ) : (
        <ol className={styles.timeline} role="list">
          {visible.length === 0 ? (
            <li className={styles.noMatches}>
              {copy.noMatches} “{searchQuery.trim()}”.
            </li>
          ) : null}
          {visible.map((entry) => {
            const agentCopy = getAgentCopy(locale, entry.agent);
            const tools = formatToolList(entry.toolCalls);
            const cost = formatCost(entry.totalCost);
            return (
              <motion.li
                key={entry.id}
                className={[styles.row, styles[`severity_${entry.severity}`]].join(" ")}
                variants={terminalLineIn}
                initial="hidden"
                animate="visible"
              >
                <div className={styles.rowTop}>
                  <span
                    className={[styles.agentBadge, styles[`agent_${entry.agent}`]].join(" ")}
                  >
                    {agentCopy.shortLabel}
                  </span>
                  <span className={styles.eventLabel}>{entry.event.replace(/_/g, " ")}</span>
                  {entry.iteration !== null ? (
                    <span className={styles.iteration}>{copy.iter} {entry.iteration}</span>
                  ) : null}
                  <span className={styles.timestamp}>
                    <Clock size={11} strokeWidth={1.75} aria-hidden="true" />
                    {formatTime(entry.timestamp)}
                  </span>
                </div>

                <h3 className={styles.rowTitle}>{entry.title}</h3>
                {entry.detail ? (
                  <p className={styles.rowDetail}>{entry.detail}</p>
                ) : null}

                {tools.length > 0 ? (
                  <ul className={styles.toolChips} aria-label={copy.toolCalls}>
                    {tools.map((tool) => (
                      <li key={tool} className={styles.toolChip}>
                        {tool}
                      </li>
                    ))}
                  </ul>
                ) : null}

                <div className={styles.rowMeta}>
                  {cost ? <span className={styles.cost}>{cost}</span> : null}
                  {entry.severity === "error" && entry.detail ? (
                    <span className={styles.errorBadge}>
                      <AlertTriangle size={11} strokeWidth={2} aria-hidden="true" />
                      {entry.detail}
                    </span>
                  ) : null}
                </div>
              </motion.li>
            );
          })}
        </ol>
      )}

      <footer className={styles.footer}>
        {copy.showing} {visible.length} {copy.of} {activity.length} {copy.events}
      </footer>
    </section>
  );
}

export default AgentActivityTimeline;
