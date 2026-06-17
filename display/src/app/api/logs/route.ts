import { NextResponse } from "next/server";
import { readLogsForSession } from "@/lib/log-parser";
import { assertSafeSessionId } from "@/lib/validators";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const sessionId = url.searchParams.get("sessionId");
  try {
    const id = assertSafeSessionId(sessionId);
    const logs = await readLogsForSession(id);
    return NextResponse.json(logs);
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Invalid request" },
      { status: 400 }
    );
  }
}
