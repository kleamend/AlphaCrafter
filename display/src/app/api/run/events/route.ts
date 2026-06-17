import { getRunStatus } from "@/lib/process-manager";
import { onRunEvent, type RunEvent } from "@/lib/run-events";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SSE_HEADERS = {
  "Content-Type": "text/event-stream",
  "Cache-Control": "no-cache, no-transform",
  "Connection": "keep-alive",
};

function formatEvent(event: RunEvent): string {
  const payload = JSON.stringify(event);
  return `event: message\ndata: ${payload}\n\n`;
}

export async function GET(request: Request): Promise<Response> {
  const encoder = new TextEncoder();
  let unsubscribe: (() => void) | null = null;
  let heartbeat: ReturnType<typeof setInterval> | null = null;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const safeEnqueue = (chunk: string) => {
        try {
          controller.enqueue(encoder.encode(chunk));
        } catch {
          // Stream already closed; nothing to do.
        }
      };

      // Initial status snapshot so clients render immediately.
      const initialEvent: RunEvent = {
        type: "status",
        status: getRunStatus(),
        at: new Date().toISOString(),
      };
      safeEnqueue(formatEvent(initialEvent));

      unsubscribe = onRunEvent((event) => {
        safeEnqueue(formatEvent(event));
      });

      // Keep the connection alive through proxies.
      heartbeat = setInterval(() => {
        safeEnqueue(": keepalive\n\n");
      }, 15_000);

      const onAbort = () => {
        if (unsubscribe) {
          unsubscribe();
          unsubscribe = null;
        }
        if (heartbeat) {
          clearInterval(heartbeat);
          heartbeat = null;
        }
        try {
          controller.close();
        } catch {
          // Already closed.
        }
      };
      request.signal.addEventListener("abort", onAbort);
    },
    cancel() {
      if (unsubscribe) {
        unsubscribe();
        unsubscribe = null;
      }
      if (heartbeat) {
        clearInterval(heartbeat);
        heartbeat = null;
      }
    },
  });

  return new Response(stream, { headers: SSE_HEADERS });
}
