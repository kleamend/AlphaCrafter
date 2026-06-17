import { Activity, CircleDot, Cog, ServerCog, type LucideIcon } from "lucide-react";

import type {
  HealthResponse,
  RunStatusResponse,
  SessionSummary,
} from "@/lib/schemas";
import type { StatusItem } from "@/components/StatusRail";
import { getCopy, type Locale } from "@/lib/i18n";

export type BuildStatusItemsArgs = {
  health: HealthResponse | null;
  healthError: string | null;
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  runStatus: RunStatusResponse;
  activeCycle: number | null;
  terminalLineCount: number;
  locale?: Locale;
};

export function buildStatusItems({
  health,
  healthError,
  sessions,
  selectedSessionId,
  runStatus,
  activeCycle,
  terminalLineCount,
  locale = "en",
}: BuildStatusItemsArgs): StatusItem[] {
  const copy = getCopy(locale).status;
  const environmentStatus = healthError
    ? healthError
    : health
      ? health.checks.every((check) => check.ok)
        ? copy.allChecksPassing
        : `${health.checks.filter((check) => check.ok).length}/${health.checks.length} ${copy.checks}`
      : copy.pending;
  const environmentKind: StatusItem["kind"] = healthError
    ? "down"
    : health?.ok
      ? "ok"
      : health
        ? "warn"
        : "idle";

  const session = sessions.find((entry) => entry.id === selectedSessionId) ?? null;
  const sessionStatus = !session
    ? copy.noSession
    : `${session.id} - ${session.currentDate ?? copy.noDate}`;
  const sessionKind: StatusItem["kind"] = !session
    ? "idle"
    : session.hasWorkspace && session.hasPersistent && session.hasAccount
      ? "ok"
      : "warn";

  const processStatus =
    runStatus.status === "idle"
      ? copy.idle
      : `${runStatus.status} - ${copy.cycle} ${activeCycle ?? "?"}`;
  const processKind: StatusItem["kind"] =
    runStatus.status === "running" || runStatus.status === "starting"
      ? "ok"
      : runStatus.status === "stopping"
        ? "warn"
        : runStatus.status === "failed"
          ? "down"
          : "idle";

  const logStatus =
    runStatus.status === "running"
      ? `${copy.streaming} (${terminalLineCount})`
      : runStatus.status === "idle"
        ? copy.notStreaming
        : runStatus.status;
  const logKind: StatusItem["kind"] =
    runStatus.status === "running"
      ? "ok"
      : runStatus.status === "failed"
        ? "down"
        : runStatus.status === "stopping"
          ? "warn"
          : "idle";

  return [
    { id: "environment", label: copy.environment, status: environmentStatus, kind: environmentKind, icon: ServerCog as LucideIcon },
    { id: "session", label: copy.session, status: sessionStatus, kind: sessionKind, icon: Activity as LucideIcon },
    { id: "process", label: copy.process, status: processStatus, kind: processKind, icon: Cog as LucideIcon },
    { id: "logs", label: copy.logs, status: logStatus, kind: logKind, icon: CircleDot as LucideIcon },
  ];
}
