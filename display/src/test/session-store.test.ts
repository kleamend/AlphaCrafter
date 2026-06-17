import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { listSessions } from "@/lib/session-store";

const FIXTURE_DATE = "2024-06-15";
const FIXTURE_WATCH_LIST = ["000001.SZ", "000002.SZ", "000333.SZ"];
const FIXTURE_TRADING_DAYS = [
  "2024-06-14",
  "2024-06-15",
  "2024-06-16",
];

let tmpRoot: string;

beforeAll(async () => {
  tmpRoot = await fs.mkdtemp(path.join(os.tmpdir(), "alphacrafter-session-store-"));

  const sessionDir = path.join(tmpRoot, "template_a");
  await fs.mkdir(path.join(sessionDir, "workspace"), { recursive: true });
  await fs.mkdir(path.join(sessionDir, "persistent"), { recursive: true });
  await fs.mkdir(path.join(sessionDir, "logs"), { recursive: true });

  const accountDoc = {
    watch_list: FIXTURE_WATCH_LIST,
    positions: [],
    cash: 100000,
  };
  await fs.writeFile(
    path.join(sessionDir, "persistent", "account.json"),
    JSON.stringify(accountDoc),
    "utf-8"
  );

  const dateDoc = {
    current_date: FIXTURE_DATE,
    trading_days: FIXTURE_TRADING_DAYS,
  };
  await fs.writeFile(
    path.join(sessionDir, "persistent", "date.json"),
    JSON.stringify(dateDoc),
    "utf-8"
  );

  const workflow = [
    { timestamp: "2024-06-15T10:00:00" },
    { timestamp: "2024-06-15T11:00:00" },
  ];
  await fs.writeFile(
    path.join(sessionDir, "logs", "workflow.json"),
    JSON.stringify(workflow),
    "utf-8"
  );

  // Add a stray file in the sandbox root that must be ignored.
  await fs.writeFile(path.join(tmpRoot, "README.txt"), "ignore me", "utf-8");
});

afterAll(async () => {
  if (tmpRoot) {
    await fs.rm(tmpRoot, { recursive: true, force: true });
  }
});

describe("listSessions", () => {
  it("returns one session with parsed metadata", async () => {
    const sessions = await listSessions(tmpRoot);

    expect(sessions).toHaveLength(1);
    const session = sessions[0];
    expect(session.id).toBe("template_a");
    expect(session.hasWorkspace).toBe(true);
    expect(session.hasPersistent).toBe(true);
    expect(session.hasAccount).toBe(true);
    expect(session.hasDate).toBe(true);
    expect(session.hasLogs).toBe(true);
    expect(session.currentDate).toBe(FIXTURE_DATE);
    expect(session.watchListSize).toBe(FIXTURE_WATCH_LIST.length);
    expect(session.lastWorkflowEventAt).toBe("2024-06-15T11:00:00");
  });
});
