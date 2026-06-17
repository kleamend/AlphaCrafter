import { describe, expect, it } from "vitest";

import { assertPathInside } from "@/lib/repo-paths";

describe("assertPathInside", () => {
  it("passes when target is inside parent", () => {
    const result = assertPathInside("/a/b", "/a/b/c.txt");
    expect(result).toBe("/a/b/c.txt");
  });

  it("throws when target escapes parent", () => {
    expect(() => assertPathInside("/a/b", "/a/secret.txt")).toThrow();
  });
});