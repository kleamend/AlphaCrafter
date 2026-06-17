"use client";

import { useMemo } from "react";

import { getAgentMeta } from "@/lib/agent-meta";
import type { AgentPhase, ParsedAgentActivity } from "@/lib/schemas";

import {
  OutputBlock,
  formatCost,
  formatSuccess,
  formatTime,
  rowMatches,
  successClass,
} from "./agent-output-helpers";
import type { OutputRow, WorkflowRow } from "./agent-output-types";

import styles from "./AgentOutputPanel.module.css";

export function WorkflowRows({ rows, query }: { rows: WorkflowRow[]; query: string }) {
  const visible = useMemo(
    () => rows.filter((row) => rowMatches(row, query)),
    [rows, query]
  );
  if (rows.length === 0) {
    return <p className={styles.empty}>No workflow phases recorded for this session yet.</p>;
  }
  if (visible.length === 0) {
    return <p className={styles.empty}>No workflow rows match “{query.trim()}”.</p>;
  }
  return (
    <ul className={styles.eventList} role="list">
      {visible.map((row) => (
        <li key={row.id} className={styles.eventRow}>
          <div className={styles.eventHeader}>
            <span className={styles.eventMeta}>
              cycle {row.cycle ?? "?"} · phase {row.phase}
            </span>
            <span className={[styles.successBadge, successClass(row.success)].join(" ")}>
              {formatSuccess(row.success)}
            </span>
            <span className={styles.eventTime}>{formatTime(row.timestamp)}</span>
          </div>
          <OutputBlock text={row.outputText} id={row.id} />
        </li>
      ))}
    </ul>
  );
}

export function ActivityRows({
  activity,
  query,
}: {
  activity: ParsedAgentActivity[];
  query: string;
}) {
  const visible = useMemo(() => {
    if (query.length === 0) return activity;
    return activity.filter((entry) => {
      const haystack = [
        entry.title,
        entry.detail,
        entry.agent,
        entry.event,
        ...entry.toolCalls.map((tool) => `${tool.name} ${tool.argumentsPreview}`),
      ]
        .join(" \n ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [activity, query]);
  if (activity.length === 0) {
    return <p className={styles.empty}>No cross-agent activity recorded yet.</p>;
  }
  if (visible.length === 0) {
    return <p className={styles.empty}>No activity matches “{query.trim()}”.</p>;
  }
  return (
    <ul className={styles.eventList} role="list">
      {visible.map((entry) => {
        const meta = getAgentMeta(entry.agent);
        return (
          <li key={entry.id} className={styles.eventRow}>
            <div className={styles.eventHeader}>
              <span className={styles.eventName}>{entry.event}</span>
              <span className={styles.eventMeta}>{meta.shortLabel}</span>
              {entry.iteration !== null ? (
                <span className={styles.iteration}>iter {entry.iteration}</span>
              ) : null}
              {entry.totalCost !== null ? (
                <span className={styles.costTag}>{formatCost(entry.totalCost)}</span>
              ) : null}
              <span className={styles.eventTime}>{formatTime(entry.timestamp)}</span>
            </div>
            {entry.detail ? <p className={styles.argsPreview}>{entry.detail}</p> : null}
          </li>
        );
      })}
    </ul>
  );
}

export function AgentRows({
  agent,
  rows,
  query,
}: {
  agent: AgentPhase;
  rows: OutputRow[];
  query: string;
}) {
  const visible = useMemo(
    () => rows.filter((row) => rowMatches(row, query)),
    [rows, query]
  );
  const meta = getAgentMeta(agent);
  if (rows.length === 0) {
    return (
      <p className={styles.empty}>
        No events recorded for the {meta.shortLabel} agent in this session.
      </p>
    );
  }
  if (visible.length === 0) {
    return <p className={styles.empty}>No rows match “{query.trim()}”.</p>;
  }
  return (
    <ul className={styles.eventList} role="list">
      {visible.map((row) => {
        const cost = formatCost(row.totalCost);
        return (
          <li key={row.id} className={styles.eventRow}>
            <div className={styles.eventHeader}>
              <span className={styles.eventName}>{row.event}</span>
              {row.iteration !== null ? (
                <span className={styles.iteration}>iter {row.iteration}</span>
              ) : null}
              <span className={[styles.successBadge, successClass(row.success)].join(" ")}>
                {formatSuccess(row.success)}
              </span>
              {cost ? <span className={styles.costTag}>{cost}</span> : null}
              <span className={styles.eventTime}>{formatTime(row.timestamp)}</span>
            </div>
            {row.toolCallNames.length > 0 ? (
              <div className={styles.toolRow}>
                <span className={styles.toolLabel}>tools</span>
                <ul className={styles.toolChips}>
                  {row.toolCallNames.map((name) => (
                    <li key={name} className={styles.toolChip}>
                      {name}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {row.argumentsPreview ? (
              <p className={styles.argsPreview}>{row.argumentsPreview}</p>
            ) : null}
            {row.error ? <p className={styles.errorLine}>error: {row.error}</p> : null}
            <OutputBlock text={row.outputText} id={row.id} />
          </li>
        );
      })}
    </ul>
  );
}
