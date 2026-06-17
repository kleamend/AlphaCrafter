import { NextResponse } from "next/server";

import { stopRun } from "@/lib/process-manager";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  const result = await stopRun();
  return NextResponse.json(result);
}
