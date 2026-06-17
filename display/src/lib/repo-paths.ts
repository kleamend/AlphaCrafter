import path from "node:path";

export function getDisplayRoot(): string {
  return process.cwd();
}

export function getRepoRoot(): string {
  return path.resolve(getDisplayRoot(), "..");
}

export function getAlphaCrafterRoot(): string {
  return path.join(getRepoRoot(), "alphacrafter");
}

export function getSandboxRoot(): string {
  return path.join(getAlphaCrafterRoot(), "sandbox");
}

export function getSessionRoot(sessionId: string): string {
  return path.join(getSandboxRoot(), sessionId);
}

export function getSessionLogsRoot(sessionId: string): string {
  return path.join(getSessionRoot(sessionId), "logs");
}

export function getSessionWorkspaceRoot(sessionId: string): string {
  return path.join(getSessionRoot(sessionId), "workspace");
}

export function assertPathInside(parent: string, target: string): string {
  const resolvedParent = path.resolve(parent);
  const resolvedTarget = path.resolve(target);
  const relative = path.relative(resolvedParent, resolvedTarget);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Resolved path escapes allowed root");
  }
  return resolvedTarget;
}