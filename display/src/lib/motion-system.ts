import type { Variants } from "framer-motion";

// Shared motion tokens. Every framer-motion variant in the app should
// import timing/ease from here so motion stays in one tempo.
export const motionTiming = {
  micro: 0.18,
  panel: 0.32,
  boot: 0.9,
} as const;

export const motionEase = [0.16, 1, 0.3, 1] as const;

// Panel-level enter: blur-to-focus rise for hero/dashboard surfaces.
export const panelEnter: Variants = {
  hidden: { opacity: 0, y: 18, filter: "blur(6px)" },
  visible: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: motionTiming.panel, ease: motionEase },
  },
};

// Stagger the child panels of the console shell.
export const staggerDeck: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.07,
      delayChildren: 0.08,
    },
  },
};

// One terminal/log line insertion: subtle x-slide + fade.
export const terminalLineIn: Variants = {
  hidden: { opacity: 0, x: -8 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: motionTiming.micro, ease: motionEase },
  },
};

// Agent dock state: the card pulses up when its phase becomes active.
export const agentDock: Variants = {
  idle: { opacity: 0.72, scale: 0.985 },
  active: {
    opacity: 1,
    scale: 1,
    transition: { duration: motionTiming.micro, ease: motionEase },
  },
};

// Helper: a higher-level container that staggers a deck of panels.
export const heroDeck: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.12,
      delayChildren: 0.04,
    },
  },
};

// Helper: detect prefers-reduced-motion on the client. SSR-safe.
export function isReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
