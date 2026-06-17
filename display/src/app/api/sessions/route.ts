import { NextResponse } from "next/server";

import { listSessions } from "@/lib/session-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const sessions = await listSessions();
  return NextResponse.json({ sessions });
}
