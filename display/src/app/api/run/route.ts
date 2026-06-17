import fs from "node:fs/promises";
import { NextResponse } from "next/server";

import { getSessionRoot } from "@/lib/repo-paths";
import { RunConflictError, startRun } from "@/lib/process-manager";
import type { StartRunResponse } from "@/lib/schemas";
import { assertSafeSessionId, parseBoolean, parseMaxCycles } from "@/lib/validators";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  if (!body || typeof body !== "object") {
    return NextResponse.json(
      { error: "Request body must be a JSON object" },
      { status: 400 }
    );
  }
  const raw = body as Record<string, unknown>;

  let sessionId: string;
  try {
    sessionId = assertSafeSessionId(raw.sessionId);
  } catch (err) {
    return NextResponse.json(
      { error: (err as Error).message },
      { status: 400 }
    );
  }

  let maxCycles: number;
  try {
    maxCycles = parseMaxCycles(raw.maxCycles);
  } catch (err) {
    return NextResponse.json(
      { error: (err as Error).message },
      { status: 400 }
    );
  }

  let resume = false;
  if (raw.resume !== undefined) {
    try {
      resume = parseBoolean(raw.resume);
    } catch (err) {
      return NextResponse.json(
        { error: (err as Error).message },
        { status: 400 }
      );
    }
  }

  const sessionDir = getSessionRoot(sessionId);
  try {
    const stat = await fs.stat(sessionDir);
    if (!stat.isDirectory()) {
      return NextResponse.json(
        { error: `Session path is not a directory: ${sessionDir}` },
        { status: 400 }
      );
    }
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return NextResponse.json(
        { error: `Session directory not found: ${sessionDir}` },
        { status: 400 }
      );
    }
    return NextResponse.json(
      { error: `Failed to stat session directory: ${(err as Error).message}` },
      { status: 400 }
    );
  }

  try {
    const result = await startRun({ sessionId, maxCycles, resume });
    const response: StartRunResponse = {
      runId: result.runId,
      status: result.status,
      sessionId: result.sessionId,
      commandPreview: result.commandPreview,
      startedAt: result.startedAt,
    };
    return NextResponse.json(response, { status: 200 });
  } catch (err) {
    if (err instanceof RunConflictError) {
      return NextResponse.json({ error: err.message }, { status: 409 });
    }
    return NextResponse.json(
      { error: (err as Error).message || "Failed to start run" },
      { status: 400 }
    );
  }
}
