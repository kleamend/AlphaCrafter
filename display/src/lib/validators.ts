export const SESSION_ID_PATTERN = /^[A-Za-z0-9._-]+$/;

export function isValidSessionId(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 120 && SESSION_ID_PATTERN.test(value);
}

export function parseMaxCycles(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 300) {
    throw new Error("maxCycles must be an integer between 1 and 300");
  }
  return parsed;
}

export function parseBoolean(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  throw new Error("Expected boolean value");
}

export function assertSafeSessionId(value: unknown): string {
  if (!isValidSessionId(value)) {
    throw new Error("Invalid sessionId. Use letters, numbers, dot, underscore, or dash.");
  }
  return value;
}