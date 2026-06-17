import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import {
  getAlphaCrafterRoot,
  getDisplayRoot,
  getRepoRoot,
  getSandboxRoot,
} from "@/lib/repo-paths";
import type { HealthCheck, HealthResponse } from "@/lib/schemas";

const execFileAsync = promisify(execFile);

const CONDA_ENV_NAME = "ALPHACRAFTER" as const;
const CONDA_TIMEOUT_MS = 30_000;
const REQUIRED_PICTURE_FILES = [
  "Miner_Agent.png",
  "Miner_Icon.png",
  "Screener_Agent.png",
  "Screener_Icon.png",
  "Trader_Agent.png",
  "Trader_Icon.png",
];

type ExecResult = { stdout: string; stderr: string };

async function runConda(
  args: string[],
  options: { cwd?: string } = {}
): Promise<ExecResult> {
  try {
    const result = (await execFileAsync(
      "conda",
      ["run", "-n", CONDA_ENV_NAME, ...args],
      {
        timeout: CONDA_TIMEOUT_MS,
        maxBuffer: 4 * 1024 * 1024,
        cwd: options.cwd,
      }
    )) as ExecResult;
    return { stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
  } catch (err) {
    const error = err as NodeJS.ErrnoException & {
      stdout?: string;
      stderr?: string;
      code?: string | number;
    };
    if (error.code === "ENOENT") {
      return { stdout: "", stderr: `conda executable not found: ${error.message}` };
    }
    return {
      stdout: error.stdout ?? "",
      stderr: error.stderr ?? error.message,
    };
  }
}

async function pathExists(target: string): Promise<boolean> {
  try {
    const stat = await fs.stat(target);
    return stat.isDirectory() || stat.isFile();
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return false;
    }
    throw err;
  }
}

async function checkRepoRoot(repoRoot: string): Promise<HealthCheck> {
  const ok = await pathExists(repoRoot);
  return {
    id: "repoRoot",
    label: "Repository root present",
    ok,
    detail: ok ? repoRoot : `Repository root not found at ${repoRoot}`,
  };
}

async function checkAlphacrafterMain(alphacrafterRoot: string): Promise<HealthCheck> {
  const mainPath = path.join(alphacrafterRoot, "main.py");
  const ok = await pathExists(mainPath);
  return {
    id: "alphacrafterMain",
    label: "alphacrafter/main.py present",
    ok,
    detail: ok ? mainPath : `Missing main.py at ${mainPath}`,
  };
}

async function checkPictureAssets(displayRoot: string): Promise<HealthCheck> {
  const pictureDir = path.join(displayRoot, "picture");
  const missing: string[] = [];
  for (const name of REQUIRED_PICTURE_FILES) {
    const ok = await pathExists(path.join(pictureDir, name));
    if (!ok) missing.push(name);
  }
  const ok = missing.length === 0;
  return {
    id: "pictureAssets",
    label: "Six character assets present",
    ok,
    detail: ok
      ? `All ${REQUIRED_PICTURE_FILES.length} images in ${pictureDir}`
      : `Missing images in ${pictureDir}: ${missing.join(", ")}`,
  };
}

async function checkSandboxDir(sandboxRoot: string): Promise<HealthCheck> {
  const ok = await pathExists(sandboxRoot);
  return {
    id: "sandboxDir",
    label: "sandbox directory present",
    ok,
    detail: ok ? sandboxRoot : `Sandbox directory not found at ${sandboxRoot}`,
  };
}

async function checkPythonVersion(): Promise<HealthCheck> {
  const { stdout, stderr } = await runConda(["python", "--version"]);
  const text = `${stdout} ${stderr}`.trim();
  const ok = /python/i.test(text);
  return {
    id: "pythonVersion",
    label: "Python via ALPHACRAFTER env",
    ok,
    detail: ok ? text : `Unable to read python --version (${text || "no output"})`,
  };
}

async function checkPythonDeps(): Promise<HealthCheck> {
  const script = "import openai, pandas, numpy, alphacrafter; print('ok')";
  const { stdout, stderr } = await runConda(["python", "-c", script]);
  const text = `${stdout} ${stderr}`.trim();
  const ok = text.includes("ok");
  return {
    id: "pythonDeps",
    label: "Python dependencies (openai, pandas, numpy, alphacrafter)",
    ok,
    detail: ok ? "All imports succeeded" : text || "Dependency import failed",
  };
}

async function checkCliHelp(alphacrafterRoot: string): Promise<HealthCheck> {
  const { stdout, stderr } = await runConda(["python", "main.py", "--help"], {
    cwd: alphacrafterRoot,
  });
  const text = `${stdout} ${stderr}`;
  const hasSession = text.includes("session_id");
  const hasMax = text.includes("--max-cycles");
  const ok = hasSession && hasMax;
  const missing: string[] = [];
  if (!hasSession) missing.push("session_id");
  if (!hasMax) missing.push("--max-cycles");
  return {
    id: "cliHelp",
    label: "main.py --help exposes session_id and --max-cycles",
    ok,
    detail: ok
      ? "main.py --help reports session_id and --max-cycles"
      : `Missing expected tokens: ${missing.join(", ")}`,
  };
}

async function checkValidSession(sandboxRoot: string): Promise<HealthCheck> {
  const candidates = ["template_a", "template_us"];
  const found: string[] = [];
  let hasValid = false;
  for (const name of candidates) {
    const sessionDir = path.join(sandboxRoot, name);
    const exists = await pathExists(sessionDir);
    if (!exists) continue;
    found.push(name);
    const hasPersistent = await pathExists(path.join(sessionDir, "persistent"));
    const hasAccount = await pathExists(path.join(sessionDir, "persistent", "account.json"));
    if (hasPersistent && hasAccount) {
      hasValid = true;
    }
  }
  const ok = hasValid;
  return {
    id: "validSession",
    label: "At least one session (template_a or template_us)",
    ok,
    detail: ok
      ? `Valid session present (${found.join(", ")})`
      : `No valid session among ${candidates.join(", ")}; found: ${found.join(", ") || "none"}`,
  };
}

export async function getHealth(): Promise<HealthResponse> {
  const repoRoot = getRepoRoot();
  const alphacrafterRoot = getAlphaCrafterRoot();
  const sandboxRoot = getSandboxRoot();
  const displayRoot = getDisplayRoot();

  const checks: HealthCheck[] = [];

  checks.push(await checkRepoRoot(repoRoot));
  checks.push(await checkAlphacrafterMain(alphacrafterRoot));
  checks.push(await checkPictureAssets(displayRoot));
  checks.push(await checkSandboxDir(sandboxRoot));
  checks.push(await checkPythonVersion());
  checks.push(await checkPythonDeps());
  checks.push(await checkCliHelp(alphacrafterRoot));
  checks.push(await checkValidSession(sandboxRoot));

  const allOk = checks.every((check) => check.ok);
  const pythonVersionCheck = checks.find((check) => check.id === "pythonVersion");
  const pythonVersion = pythonVersionCheck?.ok ? pythonVersionCheck.detail : null;

  return {
    ok: allOk,
    repoRoot,
    alphacrafterRoot,
    condaEnvName: CONDA_ENV_NAME,
    pythonVersion,
    checks,
  };
}
