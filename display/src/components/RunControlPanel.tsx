"use client";

import { AlertTriangle, CheckCircle, Play, RotateCw, Square } from "lucide-react";

import { SessionPicker } from "./SessionPicker";
import { getCopy, type Locale } from "@/lib/i18n";
import type { RunStatusName } from "@/lib/schemas";
import type { SessionSummary } from "@/lib/schemas";

import styles from "./RunControlPanel.module.css";

export type RunControlPanelProps = {
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
  className?: string;
  locale?: Locale;
};

const PROCESS_RUNNING: ReadonlySet<RunStatusName> = new Set([
  "starting",
  "running",
  "stopping",
]);

function statusVariant(status: RunStatusName, locale: Locale): {
  label: string;
  variant:
    | "idle"
    | "running"
    | "starting"
    | "stopping"
    | "stopped"
    | "failed"
    | "completed";
} {
  const labels = getCopy(locale).runControl.statusLabels;
  switch (status) {
    case "starting":
      return { label: labels.starting, variant: "starting" };
    case "running":
      return { label: labels.running, variant: "running" };
    case "stopping":
      return { label: labels.stopping, variant: "stopping" };
    case "stopped":
      return { label: labels.stopped, variant: "stopped" };
    case "failed":
      return { label: labels.failed, variant: "failed" };
    case "completed":
      return { label: labels.completed, variant: "completed" };
    case "idle":
    default:
      return { label: labels.idle, variant: "idle" };
  }
}

export function RunControlPanel({
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
  className,
  locale = "en",
}: RunControlPanelProps) {
  const copy = getCopy(locale).runControl;
  const processRunning = PROCESS_RUNNING.has(runStatus);
  const startDisabled =
    !selectedSessionId || processRunning || isStarting || isStopping;
  const stopDisabled = !processRunning || isStopping;
  const status = statusVariant(runStatus, locale);

  const containerClass = [styles.panel, className].filter(Boolean).join(" ");

  return (
    <section className={containerClass} aria-label="Run control panel">
      <header className={styles.header}>
        <h2 className={styles.title}>{copy.title}</h2>
        <p className={styles.hint}>
          {copy.hint}
        </p>
      </header>

      <div className={styles.controls}>
        <SessionPicker
          sessions={sessions}
          selectedSessionId={selectedSessionId}
          onChange={onSelectSession}
          disabled={processRunning}
          locale={locale}
        />

        <div className={styles.fieldRow}>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="max-cycles-input">
              {copy.maxCycles}
            </label>
            <input
              id="max-cycles-input"
              className={styles.input}
              type="number"
              inputMode="numeric"
              min={1}
              max={300}
              value={maxCycles}
              onChange={(event) => {
                const next = Number.parseInt(event.target.value, 10);
                if (Number.isFinite(next)) onMaxCyclesChange(next);
              }}
              disabled={processRunning}
            />
          </div>

          <label className={styles.checkboxRow}>
            <input
              type="checkbox"
              checked={resume}
              onChange={(event) => onResumeChange(event.target.checked)}
              disabled={processRunning}
            />
            {copy.resume}
          </label>
        </div>

        <div className={styles.statusLine} aria-live="polite">
          <span>{copy.status}</span>
          <span
            className={[
              styles.statusBadge,
              styles[`status${status.variant.charAt(0).toUpperCase()}${status.variant.slice(1)}`],
            ].join(" ")}
          >
            {status.variant === "failed" ? (
              <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
            ) : status.variant === "completed" || status.variant === "idle" ? (
              <CheckCircle size={14} strokeWidth={2} aria-hidden="true" />
            ) : null}
            {status.label}
            {isStarting ? ` (${copy.statusLabels.starting})` : null}
            {isStopping ? ` (${copy.statusLabels.stopping})` : null}
          </span>
        </div>

        {errorMessage ? (
          <div className={styles.errorMessage} role="alert">
            <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
            <span>{errorMessage}</span>
          </div>
        ) : null}

        <div className={styles.buttonRow}>
          <button
            type="button"
            className={[styles.button, styles.startButton].join(" ")}
            onClick={onStart}
            disabled={startDisabled}
          >
            <Play size={14} strokeWidth={2} aria-hidden="true" />
            {copy.start}
          </button>
          <button
            type="button"
            className={[styles.button, styles.stopButton].join(" ")}
            onClick={onStop}
            disabled={stopDisabled}
          >
            <Square size={14} strokeWidth={2} aria-hidden="true" />
            {copy.stop}
          </button>
          <button
            type="button"
            className={styles.button}
            onClick={onRefresh}
            disabled={isStarting || isStopping}
          >
            <RotateCw size={14} strokeWidth={2} aria-hidden="true" />
            {copy.refresh}
          </button>
        </div>
      </div>
    </section>
  );
}

export default RunControlPanel;
