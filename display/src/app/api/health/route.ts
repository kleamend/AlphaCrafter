import { NextResponse } from "next/server";

import { getHealth } from "@/lib/env-check";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const health = await getHealth();
  return NextResponse.json(health);
}
