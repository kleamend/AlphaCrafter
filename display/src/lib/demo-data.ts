import type { AgentPhase } from "@/lib/schemas";

export type DemoStep = {
  id: string;
  phase: AgentPhase;
  title: string;
  detail: string;
};

export const demoSteps: DemoStep[] = [
  {
    id: "demo-load-context",
    phase: "miner",
    title: "Load account and date context",
    detail:
      "Miner reads the latest account snapshot and current trading date before kicking off exploration.",
  },
  {
    id: "demo-miner-search",
    phase: "miner",
    title: "Search existing factor library",
    detail:
      "search_factor over factors/*.json to surface what is already validated for the current universe.",
  },
  {
    id: "demo-miner-validate",
    phase: "miner",
    title: "Validate factor candidate",
    detail:
      "Run IC, decile turnover, and drawdown checks against the historical window.",
  },
  {
    id: "demo-miner-persist",
    phase: "miner",
    title: "Persist factor JSON",
    detail:
      "write_file saves the vetted factor, metadata, and validation notes to factors/{factor_id}.json.",
  },
  {
    id: "demo-screener-market",
    phase: "screener",
    title: "Read market and index data",
    detail:
      "Screener pulls get_index_data and get_stock_data to characterize the current regime.",
  },
  {
    id: "demo-screener-ensemble",
    phase: "screener",
    title: "Build factor ensemble",
    detail:
      "Select factors, assign weights, and emit mining suggestions for the next Miner cycle.",
  },
  {
    id: "demo-trader-strategy",
    phase: "trader",
    title: "Write strategy.py",
    detail:
      "Trader compiles the Screener ensemble into executable strategy.py with risk guards.",
  },
  {
    id: "demo-trader-backtest",
    phase: "trader",
    title: "Run backtest",
    detail:
      "backtest executes the strategy over the configured window and returns metrics for review.",
  },
  {
    id: "demo-trader-feedback",
    phase: "trader",
    title: "Emit execution feedback to Screener",
    detail:
      "Trader hands the post-run diagnostics back to the Screener to refine the next ensemble.",
  },
];

export const demoStepCount = demoSteps.length;
