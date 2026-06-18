import type { Variants } from "framer-motion";

// Shared motion tokens. Every framer-motion variant in the app should
// import timing/ease from here so motion stays in one tempo.
export const motionTiming = {
  micro: 0.18,
  panel: 0.32,
  boot: 0.9,
} as const;

export const motionEase = [0.16, 1, 0.3, 1] as const;

function withReducedMotionFallback<T extends Variants>(variants: T): T {
  if (typeof window === "undefined" || !window.matchMedia) return variants;
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return variants;
  }
  // Strip transforms / filters / durations so the visible state is the
  // initial render. framer-motion will still apply opacity changes since
  // those are non-motion accessibility-friendly handoffs.
  const squashed: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(variants)) {
    if (key === "hidden") {
      squashed[key] = { opacity: 0 };
      continue;
    }
    const entry = (value ?? {}) as Record<string, unknown>;
    squashed[key] = {
      ...entry,
      transition: { duration: 0 },
    };
  }
  return squashed as T;
}

// Panel-level enter: blur-to-focus rise for hero/dashboard surfaces.
export const panelEnter: Variants = withReducedMotionFallback({
  hidden: { opacity: 0, y: 18, filter: "blur(6px)" },
  visible: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: motionTiming.panel, ease: motionEase },
  },
});

// Stagger the child panels of the console shell.
export const staggerDeck: Variants = withReducedMotionFallback({
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.07,
      delayChildren: 0.08,
    },
  },
});

// One terminal/log line insertion: subtle x-slide + fade.
export const terminalLineIn: Variants = withReducedMotionFallback({
  hidden: { opacity: 0, x: -8 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: motionTiming.micro, ease: motionEase },
  },
});

// Agent dock state: the card pulses up when its phase becomes active.
export const agentDock: Variants = withReducedMotionFallback({
  idle: { opacity: 0.72, scale: 0.985 },
  active: {
    opacity: 1,
    scale: 1,
    transition: { duration: motionTiming.micro, ease: motionEase },
  },
});

// Helper: a higher-level container that staggers a deck of panels.
export const heroDeck: Variants = withReducedMotionFallback({
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.12,
      delayChildren: 0.04,
    },
  },
});

// Helper: detect prefers-reduced-motion on the client. SSR-safe.
export function isReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
