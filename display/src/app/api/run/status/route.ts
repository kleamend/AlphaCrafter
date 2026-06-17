import { NextResponse } from "next/server";

import { getRunStatus } from "@/lib/process-manager";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(getRunStatus());
}
