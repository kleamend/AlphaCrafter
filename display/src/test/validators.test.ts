import { describe, expect, it } from "vitest";

import {
  assertSafeSessionId,
  isValidSessionId,
  parseBoolean,
  parseMaxCycles,
} from "@/lib/validators";

describe("isValidSessionId", () => {
  it("accepts template_a", () => {
    expect(isValidSessionId("template_a")).toBe(true);
  });

  it("accepts gpt-5.3-backtest-csi300", () => {
    expect(isValidSessionId("gpt-5.3-backtest-csi300")).toBe(true);
  });

  it("rejects ../secret", () => {
    expect(isValidSessionId("../secret")).toBe(false);
  });

  it("rejects /tmp/file", () => {
    expect(isValidSessionId("/tmp/file")).toBe(false);
  });

  it("rejects empty string", () => {
    expect(isValidSessionId("")).toBe(false);
  });
});

describe("assertSafeSessionId", () => {
  it("returns the value when valid", () => {
    expect(assertSafeSessionId("template_a")).toBe("template_a");
  });

  it("throws for invalid session id", () => {
    expect(() => assertSafeSessionId("../secret")).toThrow();
  });
});

describe("parseMaxCycles", () => {
  it("accepts a valid integer", () => {
    expect(parseMaxCycles(10)).toBe(10);
    expect(parseMaxCycles("25")).toBe(25);
  });

  it("rejects 0", () => {
    expect(() => parseMaxCycles(0)).toThrow();
  });

  it("rejects 301", () => {
    expect(() => parseMaxCycles(301)).toThrow();
  });

  it("rejects 1.5", () => {
    expect(() => parseMaxCycles(1.5)).toThrow();
  });
});

describe("parseBoolean", () => {
  it("accepts native booleans", () => {
    expect(parseBoolean(true)).toBe(true);
    expect(parseBoolean(false)).toBe(false);
  });

  it("accepts string booleans", () => {
    expect(parseBoolean("true")).toBe(true);
    expect(parseBoolean("false")).toBe(false);
  });

  it("throws on other values", () => {
    expect(() => parseBoolean("yes")).toThrow();
    expect(() => parseBoolean(1)).toThrow();
  });
});