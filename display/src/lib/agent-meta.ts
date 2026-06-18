import type { StaticImageData } from "next/image";

import type { AgentPhase, RunStatusName } from "@/lib/schemas";

import minerAgent from "../../picture/Miner_Agent.png";
import minerIcon from "../../picture/Miner_Icon.png";
import screenerAgent from "../../picture/Screener_Agent.png";
import screenerIcon from "../../picture/Screener_Icon.png";
import traderAgent from "../../picture/Trader_Agent.png";
import traderIcon from "../../picture/Trader_Icon.png";

type ArtRef = {
  src: StaticImageData | string;
  width: number;
  height: number;
  alt: string;
};

export type AgentMeta = {
  id: AgentPhase;
  role: string;
  shortLabel: string;
  tagline: string;
  accentVar: string;
  accentSoftVar: string;
  responsibilities: string[];
  tools: string[];
  artwork: ArtRef;
  icon: ArtRef;
};

const ART_DIMENSION = 1024;
const ICON_DIMENSION = 256;

// Single source of truth for the Miner -> Screener -> Trader order. Anywhere
// that needs to walk, sort, or look up the "next" phase should import this
// constant rather than redeclaring it.
export const PHASE_ORDER: ReadonlyArray<AgentPhase> = ["miner", "screener", "trader"];

// Process status values that mean a run is currently in flight (starting,
// running, or stopping). Replaces the four previously-redundant definitions
// of "is the process active" across the codebase.
const ACTIVE_STATUS_NAMES: ReadonlySet<RunStatusName> = new Set([
  "starting",
  "running",
  "stopping",
]);

export function isActiveRunStatus(status: string | RunStatusName | null | undefined): boolean {
  if (!status) return false;
  return ACTIVE_STATUS_NAMES.has(status as RunStatusName);
}

const AGENT_META: Record<AgentPhase, AgentMeta> = {
  miner: {
    id: "miner",
    role: "Factor Miner",
    shortLabel: "Miner",
    tagline: "Explore the factor frontier and ship durable alpha.",
    accentVar: "var(--miner)",
    accentSoftVar: "var(--miner-soft)",
    responsibilities: [
      "Factor exploration across market, fundamental, and alternative data.",
      "Information coefficient validation with cross-sectional robustness checks.",
      "Persistence of vetted factors to factors/{factor_id}.json with metadata.",
    ],
    tools: ["read_file", "write_file", "shell", "search_factor"],
    artwork: {
      src: minerAgent,
      width: ART_DIMENSION,
      height: ART_DIMENSION,
      alt: "Factor Miner agent illustration",
    },
    icon: {
      src: minerIcon,
      width: ICON_DIMENSION,
      height: ICON_DIMENSION,
      alt: "Factor Miner icon",
    },
  },
  screener: {
    id: "screener",
    role: "Factor Screener",
    shortLabel: "Screener",
    tagline: "Translate regime into a focused, defensible factor basket.",
    accentVar: "var(--screener)",
    accentSoftVar: "var(--screener-soft)",
    responsibilities: [
      "Regime assessment using market and index context.",
      "Factor selection by IC, turnover, and regime fit.",
      "Ensemble construction with weighting and decay logic.",
      "Mining suggestions fed back to the Miner for the next cycle.",
    ],
    tools: [
      "shell",
      "get_stock_data",
      "get_index_data",
      "search_factor",
      "get_financial_statements",
      "get_news",
    ],
    artwork: {
      src: screenerAgent,
      width: ART_DIMENSION,
      height: ART_DIMENSION,
      alt: "Factor Screener agent illustration",
    },
    icon: {
      src: screenerIcon,
      width: ICON_DIMENSION,
      height: ICON_DIMENSION,
      alt: "Factor Screener icon",
    },
  },
  trader: {
    id: "trader",
    role: "Strategy Trader",
    shortLabel: "Trader",
    tagline: "Compile strategy.py, run the backtest, and steer execution.",
    accentVar: "var(--trader)",
    accentSoftVar: "var(--trader-soft)",
    responsibilities: [
      "Strategy.py generation from the Screener ensemble.",
      "Backtest execution and post-run review.",
      "Step the simulation forward one cycle at a time.",
      "Execution feedback relayed back to the Screener.",
    ],
    tools: ["read_file", "write_file", "backtest", "step"],
    artwork: {
      src: traderAgent,
      width: ART_DIMENSION,
      height: ART_DIMENSION,
      alt: "Strategy Trader agent illustration",
    },
    icon: {
      src: traderIcon,
      width: ICON_DIMENSION,
      height: ICON_DIMENSION,
      alt: "Strategy Trader icon",
    },
  },
};

export function getAgentMeta(agentId: AgentPhase): AgentMeta {
  return AGENT_META[agentId];
}

export function listAgentMeta(): AgentMeta[] {
  return [AGENT_META.miner, AGENT_META.screener, AGENT_META.trader];
}
