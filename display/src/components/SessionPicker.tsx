"use client";

import { CheckCircle, AlertTriangle, CircleDot } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { SessionSummary } from "@/lib/schemas";
import { getCopy, type Locale } from "@/lib/i18n";

import styles from "./SessionPicker.module.css";

export type SessionPickerProps = {
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  onChange: (sessionId: string) => void;
  disabled?: boolean;
  locale?: Locale;
};

type ReadinessState = {
  label: string;
  variant: "ready" | "partial" | "empty";
  Icon: LucideIcon;
};

function readinessFor(session: SessionSummary | null, locale: Locale): ReadinessState {
  const runCopy = getCopy(locale).runControl;
  if (!session) {
    return { label: runCopy.noSessions, variant: "empty", Icon: CircleDot };
  }
  const ready = session.hasWorkspace && session.hasPersistent && session.hasAccount;
  if (ready) {
    return { label: runCopy.ready, variant: "ready", Icon: CheckCircle };
  }
  return { label: locale === "zh" ? "部分就绪" : "Partial", variant: "partial", Icon: AlertTriangle };
}

export function SessionPicker({
  sessions,
  selectedSessionId,
  onChange,
  disabled = false,
  locale = "en",
}: SessionPickerProps) {
  const copy = getCopy(locale).runControl;
  const selected =
    sessions.find((entry) => entry.id === selectedSessionId) ?? null;
  const readiness = readinessFor(selected, locale);
  const ReadinessIcon = readiness.Icon;

  return (
    <div className={styles.wrapper}>
      <label className={styles.label} htmlFor="session-picker">
        {copy.session}
      </label>
      <select
        id="session-picker"
        className={styles.select}
        value={selectedSessionId ?? ""}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || sessions.length === 0}
        aria-label={copy.chooseSession}
      >
        {sessions.length === 0 ? (
          <option value="">{copy.noSessions}</option>
        ) : (
          <>
            <option value="" disabled>
              {copy.chooseSession}
            </option>
            {sessions.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.id}
              </option>
            ))}
          </>
        )}
      </select>

      {selected ? (
        <div className={styles.optionMeta} aria-live="polite">
          <span className={styles.optionId}>{selected.id}</span>
          <span>{copy.date}: {selected.currentDate ?? (locale === "zh" ? "未知" : "unknown")}</span>
          <span>
            {copy.watchList}:{" "}
            {selected.watchListSize === null ? "n/a" : selected.watchListSize}
          </span>
          <span
            className={[
              styles.readiness,
              styles[
                `readiness${
                  readiness.variant === "ready"
                    ? "Ready"
                    : readiness.variant === "partial"
                      ? "Partial"
                      : "Empty"
                }`
              ],
            ].join(" ")}
          >
            <ReadinessIcon size={12} strokeWidth={2} aria-hidden="true" />
            {readiness.label}
          </span>
        </div>
      ) : (
        <span className={styles.empty}>
          {locale === "zh"
            ? "选择一个会话以加载日期、股票池和运行上下文。"
            : "Pick a session to load date, watch list, and run context."}
        </span>
      )}
    </div>
  );
}

export default SessionPicker;
