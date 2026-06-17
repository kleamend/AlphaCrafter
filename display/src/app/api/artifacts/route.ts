import { NextResponse } from "next/server";
import { readArtifactsForSession } from "@/lib/artifact-reader";
import { assertSafeSessionId } from "@/lib/validators";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const sessionId = url.searchParams.get("sessionId");
  try {
    const id = assertSafeSessionId(sessionId);
    const artifacts = await readArtifactsForSession(id);
    return NextResponse.json(artifacts);
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Invalid request" },
      { status: 400 }
    );
  }
}
