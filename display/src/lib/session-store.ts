import fs from "node:fs/promises";
import path from "node:path";

import { getSandboxRoot } from "@/lib/repo-paths";
import type { SessionSummary } from "@/lib/schemas";

const WORKFLOW_LOG_FILE = "workflow.json";

async function pathExists(target: string): Promise<boolean> {
  try {
    const stat = await fs.stat(target);
    return stat.isDirectory() || stat.isFile();
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return false;
    }
    throw err;
  }
}

async function readJsonSafe<T>(filePath: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return null;
    }
    console.warn(`[session-store] failed to read ${filePath}:`, err);
    return null;
  }
}

function readArrayLength(value: unknown): number | null {
  if (Array.isArray(value)) return value.length;
  return null;
}

function readStringField(value: unknown, key: string): string | null {
  if (value && typeof value === "object" && key in (value as Record<string, unknown>)) {
    const field = (value as Record<string, unknown>)[key];
    if (typeof field === "string") return field;
  }
  return null;
}

function readLatestWorkflowTimestamp(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  let latest: string | null = null;
  for (const entry of value) {
    if (entry && typeof entry === "object" && "timestamp" in entry) {
      const ts = (entry as Record<string, unknown>).timestamp;
      if (typeof ts === "string") {
        if (latest === null || ts > latest) {
          latest = ts;
        }
      }
    }
  }
  return latest;
}

export async function listSessions(
  sandboxRoot: string = getSandboxRoot()
): Promise<SessionSummary[]> {
  let entries: string[];
  try {
    entries = await fs.readdir(sandboxRoot);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }
    throw err;
  }

  const summaries: SessionSummary[] = [];

  for (const name of entries) {
    if (name.startsWith(".")) continue;
    const sessionDir = path.join(sandboxRoot, name);
    const stat = await fs.stat(sessionDir).catch(() => null);
    if (!stat || !stat.isDirectory()) continue;

    const workspaceDir = path.join(sessionDir, "workspace");
    const persistentDir = path.join(sessionDir, "persistent");
    const accountPath = path.join(persistentDir, "account.json");
    const datePath = path.join(persistentDir, "date.json");
    const logsDir = path.join(sessionDir, "logs");
    const workflowPath = path.join(logsDir, WORKFLOW_LOG_FILE);

    const [hasWorkspace, hasPersistent, hasAccount, hasDate, hasLogs] = await Promise.all([
      pathExists(workspaceDir),
      pathExists(persistentDir),
      pathExists(accountPath),
      pathExists(datePath),
      pathExists(logsDir),
    ]);

    const account = hasAccount ? await readJsonSafe<Record<string, unknown>>(accountPath) : null;
    const dateDoc = hasDate ? await readJsonSafe<Record<string, unknown>>(datePath) : null;
    const workflow = hasLogs ? await readJsonSafe<unknown>(workflowPath) : null;

    const currentDate = dateDoc ? readStringField(dateDoc, "current_date") : null;
    const watchListSize = account
      ? readArrayLength((account as Record<string, unknown>).watch_list)
      : null;
    const lastWorkflowEventAt = hasLogs ? readLatestWorkflowTimestamp(workflow) : null;

    summaries.push({
      id: name,
      hasWorkspace,
      hasPersistent,
      hasAccount,
      hasDate,
      hasLogs,
      currentDate,
      watchListSize,
      lastWorkflowEventAt,
    });
  }

  summaries.sort((a, b) => a.id.localeCompare(b.id));
  return summaries;
}
