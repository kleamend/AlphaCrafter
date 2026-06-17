"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";

import type { AgentPhase, LogsResponse, ParsedWorkflow } from "@/lib/schemas";

import type { OutputRow, WorkflowRow } from "./agent-output-types";

import styles from "./AgentOutputPanel.module.css";

export const COLLAPSE_THRESHOLD = 1200;

export function formatTime(at: string | null): string {
  if (!at) return "—";
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return at;
  const hh = date.getHours().toString().padStart(2, "0");
  const mm = date.getMinutes().toString().padStart(2, "0");
  const ss = date.getSeconds().toString().padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function formatSuccess(value: boolean | null): string {
  if (value === null) return "—";
  return value ? "success" : "failed";
}

export function formatCost(value: number | null): string | null {
  if (value === null) return null;
  return `$${value.toFixed(4)}`;
}

function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max)}...`;
}

function copyText(value: string): void {
  if (typeof navigator !== "undefined" && navigator.clipboard) {
    void navigator.clipboard.writeText(value).catch(() => {
      /* noop */
    });
  }
}

export function rowMatches(row: OutputRow | WorkflowRow, query: string): boolean {
  if (query.length === 0) return true;
  const isAgent = "toolCallNames" in row;
  const parts: string[] = [row.outputText];
  if (isAgent) {
    parts.push(row.event, row.toolCallNames.join(" "), row.argumentsPreview, row.error ?? "");
  } else {
    parts.push(row.phase);
  }
  return parts.join(" \n ").toLowerCase().includes(query);
}

export function successClass(value: boolean | null): string {
  if (value === true) return styles.successOk;
  if (value === false) return styles.successFail;
  return styles.successNeutral;
}

export function OutputBlock({ text, id }: { text: string; id: string }) {
  const shouldCollapse = text.length > COLLAPSE_THRESHOLD;
  const [expanded, setExpanded] = useState(false);
  const display = shouldCollapse && !expanded ? truncate(text, COLLAPSE_THRESHOLD) : text;
  if (text.length === 0) {
    return <p className={styles.outputEmpty}>No output captured.</p>;
  }
  return (
    <div className={styles.outputBlock}>
      <pre className={styles.outputText}>{display}</pre>
      <div className={styles.outputActions}>
        {shouldCollapse ? (
          <button
            type="button"
            className={styles.outputToggle}
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            aria-controls={`${id}-output`}
          >
            {expanded ? (
              <ChevronDown size={12} strokeWidth={2} aria-hidden="true" />
            ) : (
              <ChevronRight size={12} strokeWidth={2} aria-hidden="true" />
            )}
            {expanded ? "Collapse" : `Expand (${text.length - COLLAPSE_THRESHOLD} more)`}
          </button>
        ) : null}
        <button
          type="button"
          className={styles.outputToggle}
          onClick={() => copyText(text)}
          aria-label={`Copy output for ${id}`}
        >
          <Copy size={12} strokeWidth={2} aria-hidden="true" />
          Copy
        </button>
      </div>
    </div>
  );
}

export function buildAgentRows(
  agent: AgentPhase,
  log: LogsResponse["agents"]["miner"] | undefined
): OutputRow[] {
  if (!log) return [];
  return log.events.map((entry, index) => {
    const toolNames = entry.toolCalls.map((tool) => tool.name);
    const argsPreview = entry.toolCalls
      .map((tool) => `${tool.name}(${tool.argumentsPreview})`)
      .join(", ");
    return {
      id: `${agent}-${index}`,
      event: entry.event,
      success: entry.success,
      iteration: entry.iteration,
      toolCallNames: toolNames,
      argumentsPreview: argsPreview,
      totalCost: entry.totalCost,
      error: entry.error,
      timestamp: entry.timestamp,
      outputText: entry.outputText ?? entry.summary ?? "",
    };
  });
}

export function buildWorkflowRows(workflow: ParsedWorkflow | null): WorkflowRow[] {
  if (!workflow) return [];
  return workflow.phases.map((entry, index) => ({
    id: `workflow-${index}`,
    cycle: entry.cycle,
    phase: entry.phase,
    success: entry.success,
    timestamp: entry.timestamp,
    outputText: entry.outputText,
  }));
}
