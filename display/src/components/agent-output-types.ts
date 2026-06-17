export type OutputRow = {
  id: string;
  event: string;
  success: boolean | null;
  iteration: number | null;
  toolCallNames: string[];
  argumentsPreview: string;
  totalCost: number | null;
  error: string | null;
  timestamp: string | null;
  outputText: string;
};

export type WorkflowRow = {
  id: string;
  cycle: number | null;
  phase: string;
  success: boolean | null;
  timestamp: string | null;
  outputText: string;
};
