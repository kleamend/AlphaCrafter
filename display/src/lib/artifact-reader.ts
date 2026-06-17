import fs from "node:fs/promises";
import path from "node:path";

import { assertPathInside, getSessionLogsRoot, getSessionRoot, getSessionWorkspaceRoot } from "@/lib/repo-paths";
import type { ArtifactSummary, ArtifactsResponse } from "@/lib/schemas";

const PREVIEW_MAX_CHARS = 6000;
const ALLOWED_LOG_FILES = [
  "workflow.json",
  "miner_agent.json",
  "screener_agent.json",
  "trader_agent.json",
  "snapshot.json",
  "backtest_results.json",
];

type ArtifactKind = ArtifactSummary["kind"];

function makeId(kind: ArtifactKind, rel: string): string {
  return `${kind}:${rel}`;
}

function formatPreview(raw: string, originalLength: number): string {
  if (raw.length >= originalLength && raw.length <= PREVIEW_MAX_CHARS) {
    return raw;
  }
  if (raw.length > PREVIEW_MAX_CHARS) {
    return `${raw.slice(0, PREVIEW_MAX_CHARS)}\n... [truncated, original ${originalLength} chars]`;
  }
  return raw;
}

async function buildSummary(
  sessionRoot: string,
  absPath: string,
  kind: ArtifactKind,
  label: string,
  relPath: string
): Promise<ArtifactSummary | null> {
  let stat;
  try {
    stat = await fs.stat(absPath);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
  if (!stat.isFile()) return null;

  let preview = "";
  try {
    const raw = await fs.readFile(absPath, "utf-8");
    preview = formatPreview(raw, raw.length);
  } catch {
    preview = "";
  }

  return {
    id: makeId(kind, relPath),
    kind,
    label,
    relativePath: relPath,
    sizeBytes: stat.size,
    updatedAt: stat.mtime.toISOString(),
    preview,
  };
}

async function readFactors(
  sessionRoot: string,
  factorsDir: string,
  out: ArtifactSummary[]
): Promise<void> {
  let entries: string[];
  try {
    entries = await fs.readdir(factorsDir);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return;
    throw err;
  }
  for (const name of entries.sort()) {
    if (!name.toLowerCase().endsWith(".json")) continue;
    const abs = path.join(factorsDir, name);
    const rel = path.relative(sessionRoot, assertPathInside(sessionRoot, abs));
    const summary = await buildSummary(sessionRoot, abs, "factor", name, rel);
    if (summary) out.push(summary);
  }
}

export async function readArtifactsForSession(sessionId: string): Promise<ArtifactsResponse> {
  const sessionRoot = getSessionRoot(sessionId);
  const logsRoot = getSessionLogsRoot(sessionId);
  const workspaceRoot = getSessionWorkspaceRoot(sessionId);
  const persistentRoot = path.join(sessionRoot, "persistent");
  const factorsDir = path.join(workspaceRoot, "factors");

  const files: ArtifactSummary[] = [];

  // 1. workspace/strategy.py
  const strategyPath = path.join(workspaceRoot, "strategy.py");
  const strategyRel = path.relative(sessionRoot, assertPathInside(sessionRoot, strategyPath));
  const strategy = await buildSummary(sessionRoot, strategyPath, "strategy", "strategy.py", strategyRel);
  if (strategy) files.push(strategy);

  // 2. workspace/factors/*.json
  await readFactors(sessionRoot, factorsDir, files);

  // 3. persistent/account.json
  const accountPath = path.join(persistentRoot, "account.json");
  const accountRel = path.relative(sessionRoot, assertPathInside(sessionRoot, accountPath));
  const account = await buildSummary(sessionRoot, accountPath, "account", "account.json", accountRel);
  if (account) files.push(account);

  // 4. persistent/date.json
  const datePath = path.join(persistentRoot, "date.json");
  const dateRel = path.relative(sessionRoot, assertPathInside(sessionRoot, datePath));
  const date = await buildSummary(sessionRoot, datePath, "date", "date.json", dateRel);
  if (date) files.push(date);

  // 5. allowed logs
  for (const name of ALLOWED_LOG_FILES) {
    const abs = path.join(logsRoot, name);
    const rel = path.relative(sessionRoot, assertPathInside(sessionRoot, abs));
    const summary = await buildSummary(sessionRoot, abs, "log", name, rel);
    if (summary) files.push(summary);
  }

  return { files };
}
