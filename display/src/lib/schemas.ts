export type AgentPhase = "miner" | "screener" | "trader";
export type RunStatusName = "idle" | "starting" | "running" | "stopping" | "stopped" | "failed" | "completed";

export type HealthCheck = {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
};

export type HealthResponse = {
  ok: boolean;
  repoRoot: string;
  alphacrafterRoot: string;
  condaEnvName: "ALPHACRAFTER";
  pythonVersion: string | null;
  checks: HealthCheck[];
};

export type SessionSummary = {
  id: string;
  hasWorkspace: boolean;
  hasPersistent: boolean;
  hasAccount: boolean;
  hasDate: boolean;
  hasLogs: boolean;
  currentDate: string | null;
  watchListSize: number | null;
  lastWorkflowEventAt: string | null;
};

export type StartRunRequest = {
  sessionId: string;
  maxCycles: number;
  resume: boolean;
};

export type StartRunResponse = {
  runId: string;
  status: "starting" | "running";
  sessionId: string;
  commandPreview: string;
  startedAt: string;
};

export type StopRunResponse = {
  ok: boolean;
  status: "stopping" | "idle";
  message: string;
};

export type RunStatusResponse = {
  status: RunStatusName;
  runId: string | null;
  sessionId: string | null;
  startedAt: string | null;
  endedAt: string | null;
  exitCode: number | null;
  signal: string | null;
  pid: number | null;
  stdoutLineCount: number;
  stderrLineCount: number;
  lastMessage: string | null;
};

export type TerminalLine = {
  id: string;
  stream: "stdout" | "stderr" | "system";
  text: string;
  at: string;
};

export type ParsedToolCall = {
  name: string;
  argumentsPreview: string;
  callId: string | null;
};

export type ParsedWorkflowPhase = {
  cycle: number | null;
  phase: AgentPhase | "unknown";
  success: boolean | null;
  timestamp: string | null;
  outputText: string;
};

export type ParsedWorkflow = {
  phases: ParsedWorkflowPhase[];
  latestCycle: number | null;
  latestPhase: string | null;
};

export type ParsedAgentLog = {
  events: Array<{
    event: string;
    timestamp: string | null;
    iteration: number | null;
    success: boolean | null;
    totalCost: number | null;
    toolCalls: ParsedToolCall[];
    error: string | null;
    outputText: string;
  }>;
};

export type ParsedAgentActivity = {
  id: string;
  agent: AgentPhase;
  event: "run_start" | "iteration_complete" | "tool_error" | "interval_summary" | "run_complete" | "run_end" | "other";
  timestamp: string | null;
  iteration: number | null;
  title: string;
  detail: string;
  toolCalls: ParsedToolCall[];
  totalCost: number | null;
  severity: "info" | "success" | "warning" | "error";
};

export type ParsedMetricPoint = {
  label: string;
  value: number | null;
  unit: string | null;
};

export type ParsedSnapshotPoint = {
  date: string | null;
  netAssets: number | null;
  totalAssets: number | null;
  availableCash: number | null;
  marketValue: number | null;
  grossPositionRate: number | null;
  netPositionRate: number | null;
};

export type ParsedSnapshotLog = {
  points: ParsedSnapshotPoint[];
  latest: ParsedSnapshotPoint | null;
};

export type ParsedBacktestLog = {
  metrics: ParsedMetricPoint[];
  latestAt: string | null;
};

export type LogsResponse = {
  workflow: ParsedWorkflow;
  agents: {
    miner: ParsedAgentLog;
    screener: ParsedAgentLog;
    trader: ParsedAgentLog;
  };
  activity: ParsedAgentActivity[];
  snapshots: ParsedSnapshotLog;
  backtests: ParsedBacktestLog;
  warnings: string[];
};

export type ArtifactSummary = {
  id: string;
  kind: "strategy" | "factor" | "account" | "date" | "log";
  label: string;
  relativePath: string;
  sizeBytes: number;
  updatedAt: string | null;
  preview: string;
};

export type ArtifactsResponse = {
  files: ArtifactSummary[];
};