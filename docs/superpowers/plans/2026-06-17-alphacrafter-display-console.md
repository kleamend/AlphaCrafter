# AlphaCrafter Display Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `display/` 下建设一个精美的 Next.js 本地全栈控制台，让 AlphaCrafter 用户能理解系统流程、体验一轮 Agent 协作，并通过本地 `ALPHACRAFTER` Conda 环境启动、停止、观察真实运行过程。

**Architecture:** 使用 Next.js App Router 作为本地全栈应用：前端负责角色化控制台、动效、流程可视化和日志/指标展示；Route Handlers 负责本机进程管理、sandbox/session 探测、日志解析和 SSE 流式事件。Python 运行统一通过 `conda run --no-capture-output -n ALPHACRAFTER python -u main.py ...`，工作目录固定为仓库内 `alphacrafter/`，不依赖 Docker。

**Tech Stack:** Next.js App Router, React, TypeScript, CSS Modules/global CSS, next/image, lucide-react, framer-motion, Server-Sent Events, Node.js `child_process`, Vitest, Playwright.

---

## 0. 当前项目事实

MiniMax-M3 执行前必须先读这些文件，确认代码路径没有漂移：

- `README.md`: 项目定位、Docker 运行说明、sandbox/session 结构。
- `alphacrafter/main.py`: Launcher 主入口，真实运行顺序是 `Miner -> Screener -> Trader`。
- `alphacrafter/agent/instructions/miner.py`: Miner 职责与输出。
- `alphacrafter/agent/instructions/screener.py`: Screener 职责与输出。
- `alphacrafter/agent/instructions/trader.py`: Trader 职责与输出。
- `alphacrafter/agent/toolkit/backtest.py`: 回测日志、指标和状态还原语义。
- `alphacrafter/agent/toolkit/step.py`: step/snapshot 运行时指标语义。
- `alphacrafter/sim/exchange_a.py`: A 股规则、T+1、不做空、100 股整数倍。
- `alphacrafter/sim/exchange_us.py`: 美股规则、T+0、支持做空、保证金。
- `display/picture/Miner_Agent.png`
- `display/picture/Miner_Icon.png`
- `display/picture/Screener_Agent.png`
- `display/picture/Screener_Icon.png`
- `display/picture/Trader_Agent.png`
- `display/picture/Trader_Icon.png`

已探测到的本机环境事实：

- 当前 shell 是 Conda `base`。
- 存在 Conda 环境 `ALPHACRAFTER`，路径为 `/home/zhangyj/.miniconda/envs/ALPHACRAFTER`。
- `conda run -n ALPHACRAFTER python --version` 输出 `Python 3.10.20`。
- Node.js 存在，版本为 `v24.15.0`。
- npm 存在，版本为 `11.12.1`。
- `display/` 当前只包含 `picture/` 素材，没有前端脚手架。

---

## 1. 产品定位与范围

### 1.1 用户

目标用户是“使用 AlphaCrafter 系统的人”，不是只看论文介绍的访客。页面要像一个本地系统上手台，而不是营销 landing page。

### 1.2 第一版必须支持的三件事

1. **理解系统流程**  
   用户能看懂三位 Agent 的职责、工具、输入输出、上下文传递、文件产物和 daily cycle。

2. **体验一次模拟运行**  
   页面提供明确标记的 `Guided Demo` 模式，用前端动效模拟 `Miner -> Screener -> Trader` 的交接。该模式不伪装成真实运行。

3. **辅助真实使用**  
   页面能列出 sandbox session，启动真实 AlphaCrafter 进程，停止进程，查看 stdout/stderr、workflow 日志、各 Agent 日志、snapshot/backtest 指标和关键产物。

### 1.3 明确不做

- 不做公网部署能力。
- 不做 Docker 集成。
- 不在浏览器暴露 `API_KEY`、`API_URL` 或任何 `.env` 内容。
- 不允许浏览器传任意文件路径让后端读取。
- 不做多用户权限系统。
- 不做真实交易 API 接入。
- 不改 AlphaCrafter Python 核心逻辑，除非发现前端无法观测的阻塞性问题；如需改动，先写单独问题说明。
- 不移动或覆盖 `display/picture/` 原始素材。

---

## 2. 总体工程规划

### 2.1 目录结构

在 `display/` 下创建 Next.js 项目，最终结构如下：

```text
display/
  package.json
  next.config.ts
  tsconfig.json
  eslint.config.mjs
  vitest.config.ts
  playwright.config.ts
  public/
    favicon.svg
  picture/
    Miner_Agent.png
    Miner_Icon.png
    Screener_Agent.png
    Screener_Icon.png
    Trader_Agent.png
    Trader_Icon.png
  src/
    app/
      api/
        health/route.ts
        sessions/route.ts
        run/route.ts
        run/status/route.ts
        run/stop/route.ts
        run/events/route.ts
        logs/route.ts
        artifacts/route.ts
      globals.css
      layout.tsx
      page.module.css
      page.tsx
    components/
      AgentCard.tsx
      AgentActivityTimeline.tsx
      AgentOutputPanel.tsx
      ArtifactBrowser.tsx
      ConsoleClient.tsx
      DemoCyclePlayer.tsx
      FlowMap.tsx
      HeroConsole.tsx
      LiveTerminal.tsx
      MetricsPanel.tsx
      RunControlPanel.tsx
      SessionPicker.tsx
      StatusRail.tsx
    lib/
      agent-meta.ts
      artifact-reader.ts
      demo-data.ts
      env-check.ts
      log-parser.ts
      motion-system.ts
      process-manager.ts
      repo-paths.ts
      run-events.ts
      schemas.ts
      session-store.ts
      validators.ts
    test/
      fixtures/
        backtest_results.json
        miner_agent.json
        snapshot.json
        trader_agent.json
        workflow.json
      log-parser.test.ts
      validators.test.ts
      repo-paths.test.ts
      session-store.test.ts
    e2e/
      smoke.spec.ts
```

### 2.2 文件职责

- `src/lib/schemas.ts`: 前后端共享类型，不依赖 React。
- `src/lib/validators.ts`: sessionId、run config、路径白名单校验。
- `src/lib/repo-paths.ts`: 从 `display/` 定位仓库根目录、`alphacrafter/`、sandbox、picture。
- `src/lib/session-store.ts`: 扫描 `alphacrafter/sandbox/*` 并返回 session 摘要。
- `src/lib/process-manager.ts`: 单进程运行管理，封装 `child_process.spawn`。
- `src/lib/run-events.ts`: 进程事件总线和 SSE 事件格式。
- `src/lib/log-parser.ts`: 解析 workflow、Agent、snapshot、backtest JSON。
- `src/lib/motion-system.ts`: 集中定义 framer-motion variants、durations、easing、reduced-motion helpers，避免每个组件随意写动画。
- `src/lib/artifact-reader.ts`: 仅读取白名单下的日志、workspace、factors、strategy 文件。
- `src/lib/env-check.ts`: 检查 Conda 环境、Python 版本、关键路径。
- `src/lib/agent-meta.ts`: 三位 Agent 的展示文案、色彩、素材路径、工具列表。
- `src/lib/demo-data.ts`: Guided Demo 的固定脚本和示例指标。
- `src/app/api/*`: 本地 API，不访问外部网络。
- `src/components/ConsoleClient.tsx`: 唯一的主交互客户端组件，文件顶部必须写 `"use client"`；负责 React state、fetch on mount、EventSource、start/stop handlers。
- `src/components/*`: 聚焦 UI 单元，避免一个巨型页面文件。
- `src/app/page.tsx`: Server Component，只负责渲染页面壳并引入 `ConsoleClient`；不要在这里使用 `useState`、`useEffect`、`EventSource` 或浏览器 API。

---

## 3. 运行与安全边界

### 3.1 Python 启动命令

Route Handler 启动真实运行时，必须使用数组参数形式调用 `spawn`，不通过 shell 拼接命令：

```ts
const command = "conda";
const args = [
  "run",
  "--no-capture-output",
  "-n",
  "ALPHACRAFTER",
  "python",
  "-u",
  "main.py",
  sessionId,
  "--max-cycles",
  String(maxCycles),
];

if (resume) {
  args.push("--resume");
}
```

启动实现必须满足：

- `spawn` 的 `shell` 保持默认 `false`。
- 不允许用字符串拼接执行命令。
- `stdio` 使用 `["ignore", "pipe", "pipe"]`。
- `detached: true` 用于创建独立进程组，停止时必须对进程组发信号。

进程工作目录必须是：

```ts
path.join(repoRoot, "alphacrafter")
```

环境变量必须包含：

```ts
{
  ...process.env,
  PYTHONUNBUFFERED: "1"
}
```

禁止把 `process.env` 的完整内容返回给前端。

### 3.2 Session 校验

只接受满足以下规则的 sessionId：

```ts
const SESSION_ID_PATTERN = /^[A-Za-z0-9._-]+$/;
```

并且 `alphacrafter/sandbox/${sessionId}` 必须真实存在。后端读取任何 session 文件前，都要 `path.resolve` 后确认目标路径仍在该 session 目录下。

### 3.3 进程管理

第一版只允许一个真实 AlphaCrafter 进程运行：

- 如果已有进程在运行，`POST /api/run` 返回 `409 Conflict`。
- `POST /api/run/stop` 先发送 `SIGINT` 到进程组：Linux/macOS 使用 `process.kill(-child.pid, "SIGINT")`。如果进程组信号失败，再 fallback 到 `child.kill("SIGINT")`。
- 8 秒后仍未退出，再发送 `SIGTERM` 到进程组：Linux/macOS 使用 `process.kill(-child.pid, "SIGTERM")`。如果进程组信号失败，再 fallback 到 `child.kill("SIGTERM")`。
- 页面要显示 `stopping` 状态，而不是立即显示 stopped。
- Next dev HMR 可能让模块级状态重置；这不是第一版阻塞项，但页面必须能通过日志重新展示历史结果。
- `stopRun()` 必须是幂等的：没有进程、进程已经退出、重复停止请求都返回可恢复状态，不抛未捕获异常。
- 进程退出后必须清理 stop timeout，避免旧 timeout 杀到新进程。

### 3.4 日志读取

允许读取的日志路径：

- `alphacrafter/sandbox/{sessionId}/logs/workflow.json`
- `alphacrafter/sandbox/{sessionId}/logs/miner_agent.json`
- `alphacrafter/sandbox/{sessionId}/logs/screener_agent.json`
- `alphacrafter/sandbox/{sessionId}/logs/trader_agent.json`
- `alphacrafter/sandbox/{sessionId}/logs/snapshot.json`
- `alphacrafter/sandbox/{sessionId}/logs/backtest_results.json`

允许读取的产物路径：

- `alphacrafter/sandbox/{sessionId}/workspace/strategy.py`
- `alphacrafter/sandbox/{sessionId}/workspace/factors/*.json`
- `alphacrafter/sandbox/{sessionId}/persistent/account.json`
- `alphacrafter/sandbox/{sessionId}/persistent/date.json`

禁止读取：

- `.env`
- `config/models.json`
- 任意用户传入的绝对路径
- `node_modules`
- `.git`

---

## 4. 视觉设计规划

### 4.0 反 AI 味设计原则

当前项目素材有强烈角色设定和功能面板语言，不能做成常见的“AI SaaS 暗色渐变后台”。MiniMax-M3 必须把页面当成一个有世界观的本地系统控制台来设计。

**概念方向：`Quant Lab / Agent Ops Deck`**

- 关键词：二次元量化研究室、本地作战台、因子流水线、可观测 Agent 编排、精密但不冷冰冰。
- 记忆点：三位 Agent 不是装饰图，而是控制台的三个运行舱；页面动效围绕它们的交接、工具调用和日志产出展开。
- 版式：允许轻微不对称和层级叠压，例如角色图区比控制面板更有舞台感；不要使用“左大标题右插图”的普通 landing 模板。
- 纹理：可以使用细网格、扫描线、坐标刻度、数据轨迹线、面板切角、微弱噪声纹理；禁止使用大面积紫粉渐变、泛用发光 blob、随机玻璃卡片堆叠。
- 文案：直接服务使用者，避免“AI-powered / revolutionary / unlock your potential”这类泛 AI 产品话术。标题建议使用 `AlphaCrafter Console`、`Agent Operations Deck`、`Factor Cycle Control` 这类和项目本体绑定的命名。
- 图标：只用 lucide-react 或自定义 SVG 线形图标；不使用 emoji。
- 视觉验收：截图第一眼必须能看出这是 AlphaCrafter 的三 Agent 量化控制台，而不是换个 logo 就能给任何 AI 产品用的模板页。

### 4.1 总风格

采用“明亮角色素材 + 深色技术控制台”的混合风格：

- 背景：深石墨黑蓝，不做纯单色蓝，不做大面积紫色渐变。
- 主要角色色：
  - Miner: `#2F7BFF` / `#69D8FF`
  - Screener: `#F5B82E` / `#FFE5A3`
  - Trader: `#F97316` / `#FFB15C`
- 中性色：
  - Background: `#08111F`
  - Surface: `#111827`
  - Surface raised: `#172033`
  - Text primary: `#F8FAFC`
  - Text secondary: `#B9C3D6`
  - Border: `rgba(148, 163, 184, 0.22)`
- 成功/运行：`#22C55E`
- 警告：`#F59E0B`
- 错误：`#EF4444`

### 4.1.1 Typography Direction

不要默认使用 Inter、Arial、Roboto 或纯 system font 作为主要视觉字体；这些会让页面更像通用 AI 后台。

推荐字体系统：

- Display / HUD heading: `Fira Code` 或 `JetBrains Mono`，用于主标题、阶段编号、工具调用标签和指标数字。
- Body / UI text: `Fira Sans` 或 `IBM Plex Sans`，用于说明文本、按钮、表单和面板内容。
- Numeric data: 使用 `font-variant-numeric: tabular-nums`。

实现建议：

- 使用 npm 字体包 `@fontsource/fira-code` 和 `@fontsource/fira-sans`，避免本地控制台在构建或运行时依赖 Google Fonts 网络下载。
- 在 `globals.css` 顶部 import 需要的字重，例如 `@fontsource/fira-sans/400.css`、`@fontsource/fira-code/600.css`。
- 如果字体包安装失败，则退回到本地字体栈，但仍保留 CSS 变量：

```css
--font-display: "Fira Code", "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
--font-body: "Fira Sans", "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
--font-mono: "Fira Code", "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
```

字体使用规则：

- H1/H2 使用 `--font-display`，但不要全站所有文字都 monospace。
- 日志、工具调用、指标、路径使用 `--font-mono`。
- 长文本和表单使用 `--font-body`，保证可读性。
- 不使用负 letter-spacing；标题可使用轻微 uppercase 和 0.04em-0.08em 正 letter-spacing。

### 4.2 素材使用

必须使用 `display/picture/` 里的六张图：

- 首屏主视觉用三张 `*_Agent.png`。
- Agent 切换、状态 rail、输出 panel 用三张 `*_Icon.png`。
- 使用 `next/image` 静态 import，不复制、不压缩、不覆盖原图。
- 所有图片写明确 `alt`，例如 `alt="Miner agent character"`。

### 4.3 页面结构

第一屏就是可用控制台，不做纯营销 hero：

1. 顶部：产品名、环境状态、当前 session、运行状态。
2. 主体左侧：三 Agent 角色区和动态流程线。
3. 主体右侧：运行控制面板、session 选择、启动参数。
4. 下方首屏可见：实时 terminal 或阶段 timeline 的顶部。

继续向下滚动：

1. Guided Demo cycle。
2. Agent outputs tabs。
3. Metrics and backtest/snapshot charts。
4. Artifact browser。
5. 使用说明和本地环境检查结果。

### 4.4 动效要求

动效必须表达状态变化，不做无意义漂浮装饰：

- 角色卡片进入：opacity + translateY，180-260ms。
- 运行中 Agent：头像外环脉冲，周期 1.6s，使用对应角色色。
- 阶段切换：流程线从 Miner 到 Screener 到 Trader 点亮。
- 日志流：新增行淡入，最多保留 1000 行。
- 指标数字：运行完成后从旧值过渡到新值，持续 300ms。
- Guided Demo：可以手动播放/暂停/重置，不自动强迫用户观看。
- `prefers-reduced-motion: reduce` 时关闭持续动画，只保留必要状态变化。

### 4.4.1 Motion System

动效是本网站的重要组成部分，不能只作为 hover 点缀。必须实现一个完整的 motion system，让用户通过运动理解 AlphaCrafter 的运行状态。

技术选择：

- 使用 `framer-motion` 处理状态驱动的入场、阶段切换、共享布局和列表 stagger。
- 使用 CSS keyframes 处理轻量循环效果，例如运行状态脉冲、数据线流动、terminal line fade-in。
- 所有动画必须可以被 `prefers-reduced-motion` 降级。降级后保留颜色/文字状态，不保留持续运动。

必须实现的 8 个关键动效：

1. **Console boot sequence**  
   首次加载时不是整页同时出现，而是：背景网格淡入 -> 顶部状态 rail 出现 -> 三个 Agent 舱位 stagger -> 控制面板滑入 -> terminal ready line 出现。总时长 700-1100ms，可跳过 reduced motion。

2. **Agent handoff beam**  
   `Miner -> Screener -> Trader -> Miner` 的流程线必须在阶段变化时有方向性流动，使用 transform/opacity 或 SVG stroke-dashoffset，不动画 width/top/left。

3. **Active Agent dock**  
   当前 Agent 的角色图、头像环、工具 chips 同步激活；非当前 Agent 降低饱和度但保持可读。

4. **Tool call pulse**  
   当 Agent log 出现 tool call，相关 tool chip 做一次 180-260ms 的 scale/brightness pulse，并把 activity timeline 插入新行。

5. **Terminal streaming**  
   新 stdout/stderr 行逐行淡入，stderr 使用清晰文本标签和危险色边线，不只靠颜色。

6. **Metrics settle**  
   指标刷新后使用 tabular numbers 和短暂高亮，不做老虎机式数字乱跳。

7. **Guided Demo director**  
   Demo 播放时每一步都驱动 active phase、handoff beam、terminal demo line、activity timeline 和 current handoff panel；Demo 不是孤立的轮播卡片。

8. **Stop/Failure recovery motion**  
   停止、失败、完成三种状态使用不同 exit/settle 动效：stopping 为收束，failed 为短闪警示，completed 为稳定亮起。都必须有文字说明。

运动参数：

- Micro interactions: 150-260ms。
- Panel entrance: 260-420ms。
- Boot sequence: 700-1100ms。
- Easing: `cubic-bezier(0.16, 1, 0.3, 1)` 或 framer-motion spring，避免 linear。
- Continuous animation 只允许用于运行中状态和数据流，不允许多个无意义元素同时循环。

Motion QA:

- 在 1440px 和 375px 下录屏或截图检查：阶段变化必须明显但不遮挡操作。
- reduced motion 下，页面仍能表达 active phase、running/stopping/failed/completed。
- 动效不得造成布局抖动；只动画 `transform`、`opacity`、`filter`、`stroke-dashoffset`。

### 4.5 UI 约束

- 不使用 emoji 作为结构图标；使用 lucide-react。
- 不做卡片套卡片。
- 按钮、输入、选择框的高度至少 40px，主要操作 44px 以上。
- 页面在 375px、768px、1024px、1440px 宽度都不能横向溢出。
- 所有 icon-only 按钮必须有 `aria-label`。
- 所有运行状态不能只靠颜色表达，必须有文字状态。
- 长日志和长 Agent 输出必须可复制、可折叠、可搜索。

---

## 5. API 规划

### 5.1 `GET /api/health`

用途：检查本地环境。

返回：

```ts
type HealthResponse = {
  ok: boolean;
  repoRoot: string;
  alphacrafterRoot: string;
  condaEnvName: "ALPHACRAFTER";
  pythonVersion: string | null;
  checks: Array<{
    id: string;
    label: string;
    ok: boolean;
    detail: string;
  }>;
};
```

检查项：

- `repoRoot` 存在。
- `alphacrafter/main.py` 存在。
- `display/picture` 六张素材存在。
- `conda run -n ALPHACRAFTER python --version` 能执行。
- `conda run -n ALPHACRAFTER python -c "import openai, pandas, numpy, alphacrafter; print('ok')"` 能执行。
- 在 `alphacrafter/` 目录下执行 `conda run -n ALPHACRAFTER python main.py --help` 能执行，并且输出包含 `session_id` 与 `--max-cycles`。
- `alphacrafter/sandbox` 存在。

### 5.2 `GET /api/sessions`

用途：列出可运行 session。

返回：

```ts
type SessionsResponse = {
  sessions: Array<{
    id: string;
    hasWorkspace: boolean;
    hasPersistent: boolean;
    hasAccount: boolean;
    hasDate: boolean;
    hasLogs: boolean;
    currentDate: string | null;
    watchListSize: number | null;
    lastWorkflowEventAt: string | null;
  }>;
};
```

### 5.3 `POST /api/run`

用途：启动真实 AlphaCrafter。

请求：

```ts
type StartRunRequest = {
  sessionId: string;
  maxCycles: number;
  resume: boolean;
};
```

校验：

- `sessionId` 符合白名单 pattern。
- session 目录存在。
- `maxCycles` 是 1 到 300 的整数。
- 没有其他进程运行。

成功返回：

```ts
type StartRunResponse = {
  runId: string;
  status: "starting" | "running";
  sessionId: string;
  commandPreview: string;
  startedAt: string;
};
```

`commandPreview` 可以显示给用户，但不能包含环境变量。

### 5.4 `GET /api/run/status`

用途：读取当前进程状态。

返回：

```ts
type RunStatusResponse = {
  status: "idle" | "starting" | "running" | "stopping" | "stopped" | "failed" | "completed";
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
```

### 5.5 `POST /api/run/stop`

用途：停止当前真实运行。

返回：

```ts
type StopRunResponse = {
  ok: boolean;
  status: "stopping" | "idle";
  message: string;
};
```

如果没有进程，返回 `200` 和 `idle`，不要报错。

### 5.6 `GET /api/run/events`

用途：SSE 实时事件流。

事件类型：

```ts
type RunEvent =
  | { type: "status"; status: RunStatusResponse; at: string }
  | { type: "stdout"; line: string; at: string }
  | { type: "stderr"; line: string; at: string }
  | { type: "phase"; phase: "miner" | "screener" | "trader"; cycle: number | null; at: string }
  | { type: "exit"; exitCode: number | null; signal: string | null; at: string };
```

Route Handler 必须设置：

```ts
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
```

### 5.7 `GET /api/logs?sessionId=...`

用途：读取并汇总历史日志。

返回：

```ts
type LogsResponse = {
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
```

解析失败时不要让整个请求失败；在 `warnings` 中说明具体文件。

`activity` 必须从三个 Agent log 汇总，并按 timestamp 升序排序。它用于展示真实运行中的 Agent 行为，不等同于 stdout。

### 5.8 `GET /api/artifacts?sessionId=...`

用途：列出关键产物，不读取敏感配置。

返回：

```ts
type ArtifactsResponse = {
  files: Array<{
    id: string;
    kind: "strategy" | "factor" | "account" | "date" | "log";
    label: string;
    relativePath: string;
    sizeBytes: number;
    updatedAt: string | null;
    preview: string;
  }>;
};
```

`preview` 最多 6000 字符，超出后截断并显示截断说明。

---

## 6. 前端状态规划

### 6.1 页面主状态

```ts
type ConsoleViewState = {
  selectedSessionId: string | null;
  maxCycles: number;
  resume: boolean;
  mode: "guided-demo" | "real-run";
  activePhase: AgentPhase | null;
  activeCycle: number | null;
  runStatus: RunStatusResponse;
  terminalLines: Array<{
    id: string;
    stream: "stdout" | "stderr" | "system";
    text: string;
    at: string;
  }>;
  logs: LogsResponse | null;
  artifacts: ArtifactsResponse | null;
  searchQuery: string;
};
```

### 6.2 UI 分区

- `HeroConsole`: 首屏角色和流程总览。
- `ConsoleClient`: 页面交互根组件，必须是 Client Component。
- `RunControlPanel`: session、maxCycles、resume、start、stop、refresh。
- `StatusRail`: health、session、process、logs 四类状态。
- `FlowMap`: Miner/Screener/Trader 的动态流程图。
- `DemoCyclePlayer`: 前端模拟运行，不调用后端进程。
- `LiveTerminal`: stdout/stderr/SSE 日志。
- `AgentActivityTimeline`: 从 Agent JSON logs 中展示 iteration、tool calls、tool errors、cost 和 run_complete。
- `AgentOutputPanel`: workflow/agent 输出摘要。
- `MetricsPanel`: snapshot/backtest 指标。
- `ArtifactBrowser`: strategy、factors、account、date 预览。

---

## 7. 任务分解

### Task 1: 建立 Next.js 项目骨架

**Files:**
- Create: `display/package.json`
- Create: `display/next.config.ts`
- Create: `display/tsconfig.json`
- Create: `display/eslint.config.mjs`
- Create: `display/vitest.config.ts`
- Create: `display/playwright.config.ts`
- Create: `display/src/app/layout.tsx`
- Create: `display/src/app/page.tsx`
- Create: `display/src/app/globals.css`
- Create: `display/src/app/page.module.css`

- [ ] **Step 1: 确认不会覆盖素材**

Run:

```bash
find display -maxdepth 2 -type f -print | sort
```

Expected:

```text
display/picture/Miner_Agent.png
display/picture/Miner_Icon.png
display/picture/Screener_Agent.png
display/picture/Screener_Icon.png
display/picture/Trader_Agent.png
display/picture/Trader_Icon.png
```

- [ ] **Step 2: 创建 `display/package.json`**

Use this exact script baseline:

```json
{
  "name": "alphacrafter-display",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -H 127.0.0.1 -p 3000",
    "build": "next build",
    "start": "next start -H 127.0.0.1 -p 3000",
    "lint": "eslint . --max-warnings=0",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test",
    "check": "npm run lint && npm run test && npm run build"
  },
  "dependencies": {
    "@fontsource/fira-code": "^5.1.1",
    "@fontsource/fira-sans": "^5.1.1",
    "framer-motion": "^12.0.0",
    "lucide-react": "^0.468.0",
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@eslint/eslintrc": "^3.2.0",
    "@playwright/test": "^1.49.0",
    "@testing-library/jest-dom": "^6.6.0",
    "@testing-library/react": "^16.1.0",
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "eslint": "^9.17.0",
    "eslint-config-next": "^15.0.0",
    "jsdom": "^25.0.0",
    "typescript": "^5.7.0",
    "vitest": "^2.1.0"
  }
}
```

If npm reports a peer dependency mismatch, keep Next/React on the same major line and record the final installed versions in `display/package-lock.json`.

- [ ] **Step 3: 创建基础配置文件**

`display/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`display/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
```

`display/eslint.config.mjs`:

```js
import { FlatCompat } from "@eslint/eslintrc";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const compat = new FlatCompat({ baseDirectory: __dirname });

export default [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [".next/**", "node_modules/**", "playwright-report/**", "test-results/**"],
  },
];
```

`display/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/test/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
```

`display/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 5"], viewport: { width: 375, height: 812 } },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
```

- [ ] **Step 4: 安装依赖**

Run:

```bash
cd display
npm install
```

Expected:

- `display/package-lock.json` exists.
- `node_modules/` exists locally under `display/`.

- [ ] **Step 5: 创建基础 App Router 文件**

`display/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AlphaCrafter Console",
  description: "Local control console for the AlphaCrafter multi-agent trading framework.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

`display/src/app/page.tsx`:

```tsx
import styles from "./page.module.css";

export default function HomePage() {
  return (
    <main className={styles.pageShell}>
      <section className={styles.scaffoldPanel}>
        <p className={styles.kicker}>AlphaCrafter Local Console</p>
        <h1>Miner, Screener, Trader</h1>
        <p>Next.js console scaffold is ready.</p>
      </section>
    </main>
  );
}
```

`display/src/app/page.module.css`:

```css
.pageShell {
  min-height: 100dvh;
  background: #08111f;
  color: #f8fafc;
  display: grid;
  place-items: center;
  padding: 32px;
}

.scaffoldPanel {
  max-width: 760px;
}

.kicker {
  color: #69d8ff;
  font-weight: 700;
}
```

`display/src/app/globals.css`:

```css
@import "@fontsource/fira-sans/300.css";
@import "@fontsource/fira-sans/400.css";
@import "@fontsource/fira-sans/500.css";
@import "@fontsource/fira-sans/600.css";
@import "@fontsource/fira-sans/700.css";
@import "@fontsource/fira-code/400.css";
@import "@fontsource/fira-code/500.css";
@import "@fontsource/fira-code/600.css";
@import "@fontsource/fira-code/700.css";

:root {
  color-scheme: dark;
  --bg: #08111f;
  --surface: #111827;
  --surface-raised: #172033;
  --text: #f8fafc;
  --text-muted: #b9c3d6;
  --border: rgba(148, 163, 184, 0.22);
  --miner: #2f7bff;
  --miner-soft: #69d8ff;
  --screener: #f5b82e;
  --screener-soft: #ffe5a3;
  --trader: #f97316;
  --trader-soft: #ffb15c;
  --success: #22c55e;
  --warning: #f59e0b;
  --danger: #ef4444;
  --font-display: "Fira Code", "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  --font-body: "Fira Sans", "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "Fira Code", "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  --radius-sm: 8px;
  --radius-md: 12px;
  --shadow-panel: 0 24px 80px rgba(0, 0, 0, 0.28);
}

* {
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body, "Fira Sans", "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif);
  font-variant-numeric: tabular-nums;
}

button,
input,
select,
textarea {
  font: inherit;
}

button {
  cursor: pointer;
}

:focus-visible {
  outline: 3px solid var(--miner-soft);
  outline-offset: 3px;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.001ms !important;
  }
}
```

- [ ] **Step 6: 验证骨架**

Run:

```bash
cd display
npm run build
```

Expected:

- Next build succeeds.

Guarded commit:

```bash
git status --short
```

If only display scaffold files and this plan are present, commit:

```bash
git add display docs/superpowers/plans/2026-06-17-alphacrafter-display-console.md
git commit -m "feat: scaffold alphacrafter display console"
```

If unrelated user changes are present, do not commit; continue and report the changed paths.

### Task 2: 定义共享类型、校验与路径工具

**Files:**
- Create: `display/src/lib/schemas.ts`
- Create: `display/src/lib/validators.ts`
- Create: `display/src/lib/repo-paths.ts`
- Create: `display/src/test/validators.test.ts`
- Create: `display/src/test/repo-paths.test.ts`

- [ ] **Step 1: 编写共享类型**

`schemas.ts` must define these names exactly:

```ts
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
```

`schemas.ts` is the single source of truth for all API response types. `log-parser.ts`, `artifact-reader.ts`, Route Handlers, and React components must import these types from `@/lib/schemas` instead of redefining incompatible local copies.

- [ ] **Step 2: 编写校验函数**

`validators.ts` must export:

```ts
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
```

- [ ] **Step 3: 编写路径工具**

`repo-paths.ts` must export:

```ts
import path from "node:path";

export function getDisplayRoot(): string {
  return process.cwd();
}

export function getRepoRoot(): string {
  return path.resolve(getDisplayRoot(), "..");
}

export function getAlphaCrafterRoot(): string {
  return path.join(getRepoRoot(), "alphacrafter");
}

export function getSandboxRoot(): string {
  return path.join(getAlphaCrafterRoot(), "sandbox");
}

export function getSessionRoot(sessionId: string): string {
  return path.join(getSandboxRoot(), sessionId);
}

export function getSessionLogsRoot(sessionId: string): string {
  return path.join(getSessionRoot(sessionId), "logs");
}

export function getSessionWorkspaceRoot(sessionId: string): string {
  return path.join(getSessionRoot(sessionId), "workspace");
}

export function assertPathInside(parent: string, target: string): string {
  const resolvedParent = path.resolve(parent);
  const resolvedTarget = path.resolve(target);
  const relative = path.relative(resolvedParent, resolvedTarget);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Resolved path escapes allowed root");
  }
  return resolvedTarget;
}
```

- [ ] **Step 4: 写单元测试**

`validators.test.ts` must cover:

- accepts `template_a`
- accepts `gpt-5.3-backtest-csi300`
- rejects `../secret`
- rejects `/tmp/file`
- rejects empty string
- rejects `maxCycles` 0, 301, 1.5

`repo-paths.test.ts` must cover:

- `assertPathInside("/a/b", "/a/b/c.txt")` passes
- `assertPathInside("/a/b", "/a/secret.txt")` throws

- [ ] **Step 5: 验证**

Run:

```bash
cd display
npm run test
```

Expected:

- All tests pass.

### Task 3: 实现 session 扫描与环境健康检查

**Files:**
- Create: `display/src/lib/session-store.ts`
- Create: `display/src/lib/env-check.ts`
- Create: `display/src/app/api/sessions/route.ts`
- Create: `display/src/app/api/health/route.ts`
- Create: `display/src/test/session-store.test.ts`

- [ ] **Step 1: 实现 session 扫描**

`session-store.ts` must:

- Use `fs.promises`.
- Read directories under `getSandboxRoot()`.
- Ignore files.
- For each session, detect `workspace/`, `persistent/`, `persistent/account.json`, `persistent/date.json`, `logs/`.
- Parse `date.json.current_date` when present.
- Parse `account.json.watch_list.length` when present.
- Parse `logs/workflow.json` and find latest `timestamp` when present.
- Return sorted sessions by id.

- [ ] **Step 2: 写 fixture-based test**

Use `fs.mkdtemp` under `/tmp` in the test, and make `session-store.ts` accept an optional sandbox root parameter for tests:

```ts
export async function listSessions(sandboxRoot = getSandboxRoot()): Promise<SessionSummary[]> {
  // implementation
}
```

Test creates:

```text
tmpSandbox/
  template_a/
    workspace/
    persistent/account.json
    persistent/date.json
    logs/workflow.json
```

Expected:

- one session returned
- `hasWorkspace === true`
- `currentDate` equals fixture date
- `watchListSize` equals fixture watch list length

- [ ] **Step 3: 实现 health check**

`env-check.ts` must:

- Use `spawn` or `execFile` with `conda run -n ALPHACRAFTER python --version`.
- Use `spawn` or `execFile` with `conda run -n ALPHACRAFTER python -c "import openai, pandas, numpy, alphacrafter; print('ok')"` and mark dependencies failed if exit code is non-zero.
- Use `spawn` or `execFile` with `conda run -n ALPHACRAFTER python main.py --help` in cwd `getAlphaCrafterRoot()` and mark CLI failed unless output includes `session_id` and `--max-cycles`.
- Never return environment variables.
- Check six image files in `display/picture`.
- Check `alphacrafter/sandbox/template_a` and `alphacrafter/sandbox/template_us` separately; either can be missing, but at least one valid session must exist for `ok: true`.
- Return `HealthResponse`.

- [ ] **Step 4: 实现 API routes**

`src/app/api/sessions/route.ts`:

```ts
import { NextResponse } from "next/server";
import { listSessions } from "@/lib/session-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const sessions = await listSessions();
  return NextResponse.json({ sessions });
}
```

`src/app/api/health/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getHealth } from "@/lib/env-check";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const health = await getHealth();
  return NextResponse.json(health);
}
```

- [ ] **Step 5: 验证**

Run:

```bash
cd display
npm run test
npm run build
```

Expected:

- Unit tests pass.
- Build succeeds.

### Task 4: 实现进程管理与 SSE 事件总线

**Files:**
- Create: `display/src/lib/run-events.ts`
- Create: `display/src/lib/process-manager.ts`
- Create: `display/src/app/api/run/route.ts`
- Create: `display/src/app/api/run/status/route.ts`
- Create: `display/src/app/api/run/stop/route.ts`
- Create: `display/src/app/api/run/events/route.ts`

- [ ] **Step 1: 事件总线**

`run-events.ts` must use Node `EventEmitter` and export:

```ts
export type RunEvent =
  | { type: "status"; status: import("./schemas").RunStatusResponse; at: string }
  | { type: "stdout"; line: string; at: string }
  | { type: "stderr"; line: string; at: string }
  | { type: "phase"; phase: import("./schemas").AgentPhase; cycle: number | null; at: string }
  | { type: "exit"; exitCode: number | null; signal: string | null; at: string };

export const runEventEmitter = new EventEmitter();

export function emitRunEvent(event: RunEvent) {
  runEventEmitter.emit("run-event", event);
}
```

- [ ] **Step 2: 进程管理**

`process-manager.ts` must:

- Maintain module-level state.
- Allow only one active process.
- Use `spawn("conda", args, { cwd: getAlphaCrafterRoot(), env, detached: true, stdio: ["ignore", "pipe", "pipe"] })`.
- Generate `runId` with `crypto.randomUUID()`.
- Split stdout/stderr by line.
- Keep ring buffers of last 1000 stdout lines and last 500 stderr lines.
- Detect phase from stdout lines containing `MINER PHASE`, `SCREENER PHASE`, `TRADER PHASE`, `CYCLE`.
- Implement `sendSignalToRun(signal: "SIGINT" | "SIGTERM")`:

```ts
function sendSignalToRun(signal: NodeJS.Signals) {
  if (!activeRun?.child.pid) return;
  try {
    process.kill(-activeRun.child.pid, signal);
  } catch {
    activeRun.child.kill(signal);
  }
}
```

- Implement `stopRun()` so it:
  - returns idle success when no process exists
  - sets status to `stopping`
  - calls `sendSignalToRun("SIGINT")`
  - schedules one 8-second fallback timeout that calls `sendSignalToRun("SIGTERM")` only if the same `runId` is still active
  - clears the fallback timeout on process close
- On close, set status:
  - `completed` if exit code is 0.
  - `failed` if exit code is non-zero.
  - `stopped` if stop was requested.

Command args must match section 3.1.

- [ ] **Step 3: Start route**

`POST /api/run`:

- Parse JSON.
- Validate sessionId and maxCycles.
- Validate session directory exists.
- Call `startRun`.
- Return `409` if already running.

- [ ] **Step 4: Status route**

`GET /api/run/status` returns `getRunStatus()`.

- [ ] **Step 5: Stop route**

`POST /api/run/stop` calls `stopRun()` and returns `StopRunResponse`.

- [ ] **Step 6: SSE route**

`GET /api/run/events`:

- Use `ReadableStream`.
- Send an initial `status` event immediately.
- Subscribe to `runEventEmitter`.
- Format each event as:

```text
event: message
data: {"type":"stdout","line":"...","at":"..."}

```

- Remove listener on abort.
- Set headers:

```ts
{
  "Content-Type": "text/event-stream",
  "Cache-Control": "no-cache, no-transform",
  "Connection": "keep-alive"
}
```

- [ ] **Step 7: Manual API verification**

Run dev server:

```bash
cd display
npm run dev
```

In another terminal:

```bash
curl http://127.0.0.1:3000/api/run/status
curl http://127.0.0.1:3000/api/sessions
```

Expected:

- JSON responses.
- No stack trace in terminal.

### Task 5: 实现日志解析与产物读取

**Files:**
- Create: `display/src/lib/log-parser.ts`
- Create: `display/src/lib/artifact-reader.ts`
- Create: `display/src/app/api/logs/route.ts`
- Create: `display/src/app/api/artifacts/route.ts`
- Create: `display/src/test/fixtures/workflow.json`
- Create: `display/src/test/fixtures/miner_agent.json`
- Create: `display/src/test/fixtures/screener_agent.json`
- Create: `display/src/test/fixtures/trader_agent.json`
- Create: `display/src/test/fixtures/snapshot.json`
- Create: `display/src/test/fixtures/backtest_results.json`
- Create: `display/src/test/log-parser.test.ts`

- [ ] **Step 1: 实现 parser 输出**

`log-parser.ts` must import these public types from `@/lib/schemas`:

```ts
import type {
  AgentPhase,
  LogsResponse,
  ParsedAgentActivity,
  ParsedAgentLog,
  ParsedBacktestLog,
  ParsedSnapshotLog,
  ParsedToolCall,
  ParsedWorkflow,
} from "@/lib/schemas";
```

It must export parser functions, not duplicate type definitions:

```ts
export async function readLogsForSession(sessionId: string): Promise<LogsResponse> {
  // implementation
}
```

Implement defensive JSON parsing:

- If file missing, return empty data and warning.
- If JSON object, wrap as single-element array.
- If JSON invalid, return warning.
- For `iteration_complete`, read `iteration`, `total_cost`, and `tool_calls`.
- For `tool_error`, read `iteration`, `tool`, and `error`, and mark severity as `error`.
- For `interval_summary`, read `iteration`, `summary`, and `tools_executed_in_interval`.
- For `run_complete`, read `final_state.success`, `total_iterations`, `total_tool_calls`, `tools_used`, and `final_state.output_text`.
- Build `ParsedAgentActivity[]` from all three Agent logs and sort by timestamp, with entries missing timestamps placed after timestamped entries.

- [ ] **Step 2: Snapshot/backtest parser**

Extract visible metrics:

- net assets
- total assets
- available cash
- market value
- gross position rate
- net position rate
- Sharpe Ratio
- Max Drawdown
- Calmar Ratio
- Annualized Return
- Period/Total Return

All unknown numbers should become `null`, not `NaN`.

- [ ] **Step 3: Artifact reader**

`artifact-reader.ts` must:

- List strategy.py if present.
- List factors under `workspace/factors/*.json` if folder exists.
- List account/date files if present.
- List allowed logs if present.
- Preview text with max 6000 chars.
- Use `assertPathInside(sessionRoot, targetPath)`.

- [ ] **Step 4: API routes**

`GET /api/logs?sessionId=...`:

- validate sessionId
- return parser results
- include warnings

`GET /api/artifacts?sessionId=...`:

- validate sessionId
- return artifact list

- [ ] **Step 5: Tests**

Fixtures should include at least:

- workflow with three phases across one cycle
- miner agent `agent_init`
- trader `run_complete`
- snapshot with one account object
- backtest result with metrics

Run:

```bash
cd display
npm run test
```

Expected:

- Parser tests pass.
- Missing fixture path returns warnings instead of throwing.

### Task 6: 建立角色元数据与设计基础组件

**Files:**
- Create: `display/src/lib/agent-meta.ts`
- Create: `display/src/lib/demo-data.ts`
- Create: `display/src/components/AgentCard.tsx`
- Create: `display/src/components/FlowMap.tsx`
- Create: `display/src/components/HeroConsole.tsx`
- Create: `display/src/components/StatusRail.tsx`
- Modify: `display/src/app/page.tsx`
- Modify: `display/src/app/page.module.css`

- [ ] **Step 1: Agent meta**

`agent-meta.ts` must define:

- Miner:
  - role: Factor Miner
  - color tokens: blue
  - responsibilities: factor exploration, IC validation, persistence to `factors/{factor_id}.json`
  - tools: read_file, write_file, shell, search_factor
- Screener:
  - role: Factor Screener
  - responsibilities: regime assessment, factor selection, ensemble construction, mining suggestions
  - tools: shell, get_stock_data, get_index_data, search_factor, get_financial_statements, get_news
- Trader:
  - role: Strategy Trader
  - responsibilities: strategy.py generation, backtest, step, execution feedback
  - tools: read_file, write_file, backtest, step

Import images:

```ts
import minerAgent from "../../picture/Miner_Agent.png";
import minerIcon from "../../picture/Miner_Icon.png";
```

Use relative imports that compile from `display/src/lib/agent-meta.ts`.

- [ ] **Step 2: Demo data**

`demo-data.ts` provides a 9-step script:

1. Load account/date context.
2. Miner searches existing factor library.
3. Miner validates a factor candidate.
4. Miner persists factor JSON.
5. Screener reads market/index data.
6. Screener builds factor ensemble.
7. Trader writes strategy.py.
8. Trader runs backtest.
9. Trader emits feedback to Screener.

Each step includes:

```ts
{
  id: string;
  phase: "miner" | "screener" | "trader";
  title: string;
  detail: string;
}
```

- [ ] **Step 3: AgentCard**

Component props:

```ts
type AgentCardProps = {
  agentId: "miner" | "screener" | "trader";
  active: boolean;
  compact?: boolean;
};
```

Use `next/image`, role text, tool chips, and `aria-current={active ? "step" : undefined}`.

- [ ] **Step 4: FlowMap**

Show three nodes and directional lines:

`Miner -> Screener -> Trader -> feedback -> Miner`

The feedback line can be curved but must be CSS/SVG, not an external image.

- [ ] **Step 5: StatusRail**

Show four status items:

- Environment
- Session
- Process
- Logs

Each item displays label, status text, and lucide icon.

- [ ] **Step 6: Page integration**

Replace the scaffold page with:

- Header
- HeroConsole initial region using AgentCard and FlowMap
- Right side panel initial region for run controls
- Below fold initial region for demo/logs/metrics

Run:

```bash
cd display
npm run build
```

Expected:

- Build succeeds.
- Images compile through Next.

### Task 7: 实现运行控制面板与数据 hooks

**Files:**
- Create: `display/src/components/ConsoleClient.tsx`
- Create: `display/src/components/SessionPicker.tsx`
- Create: `display/src/components/RunControlPanel.tsx`
- Create: `display/src/components/LiveTerminal.tsx`
- Modify: `display/src/app/page.tsx`
- Modify: `display/src/app/page.module.css`

- [ ] **Step 1: SessionPicker**

Props:

```ts
type SessionPickerProps = {
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  onChange: (sessionId: string) => void;
  disabled?: boolean;
};
```

Display session id, current date, watchlist size, and readiness indicator.

- [ ] **Step 2: RunControlPanel**

Controls:

- session select
- maxCycles numeric input, min 1 max 300
- resume checkbox
- start button
- stop button
- refresh button

Button states:

- Start disabled if no session or process running.
- Stop disabled if no process running.
- While starting/stopping, show textual status.

Use lucide icons:

- Play
- Square
- RotateCw
- CheckCircle
- AlertTriangle

- [ ] **Step 3: Create ConsoleClient boundary**

`display/src/components/ConsoleClient.tsx` must start with:

```tsx
"use client";
```

It owns:

- all `useState` calls for `ConsoleViewState`
- all `useEffect` calls
- `fetch` calls to local APIs
- `EventSource("/api/run/events")`
- start/stop/refresh handlers
- local terminal ring buffer

`display/src/app/page.tsx` must remain a Server Component:

```tsx
import { ConsoleClient } from "@/components/ConsoleClient";
import styles from "./page.module.css";

export default function HomePage() {
  return (
    <main className={styles.pageShell}>
      <ConsoleClient />
    </main>
  );
}
```

Do not add `"use client"` to `page.tsx` unless there is a concrete build issue. The preferred boundary is a small server page and a dedicated `ConsoleClient`.

- [ ] **Step 4: Data fetching**

In `ConsoleClient.tsx`, fetch on mount:

- `/api/health`
- `/api/sessions`
- `/api/run/status`

Use plain `fetch` and React state. Do not add SWR or React Query in first version.

- [ ] **Step 5: Start/Stop handlers**

Start handler posts:

```ts
{
  sessionId: selectedSessionId,
  maxCycles,
  resume
}
```

Stop handler posts to `/api/run/stop`.

On error, show visible message in the control panel and terminal system stream.

- [ ] **Step 6: LiveTerminal**

Props:

```ts
type LiveTerminalProps = {
  lines: TerminalLine[];
  onClear: () => void;
};
```

Features:

- filter dropdown: all/stdout/stderr/system
- search input that filters visible terminal lines by case-insensitive substring
- copy all visible lines
- clear local terminal
- monospace line rendering
- stderr lines marked with text label

### Task 8: 实现 SSE 实时日志

**Files:**
- Modify: `display/src/components/ConsoleClient.tsx`
- Modify: `display/src/components/LiveTerminal.tsx`
- Modify: `display/src/components/FlowMap.tsx`

- [ ] **Step 1: 建立 EventSource**

In `ConsoleClient.tsx`, create `EventSource("/api/run/events")` on mount.

On message:

- `stdout`: append terminal line.
- `stderr`: append terminal line.
- `status`: update run status.
- `phase`: update active phase and active cycle.
- `exit`: append system line and refresh logs/artifacts.
- Every 2.5 seconds while `runStatus.status` is `starting`, `running`, or `stopping`, refresh `/api/logs?sessionId=...` so Agent activity is visible before the process exits. Clear this interval when the process is idle, stopped, completed, or failed.

On error:

- Append one system warning.
- Do not spam repeated warnings; rate limit to once every 10 seconds.

- [ ] **Step 2: Ring buffer**

Keep terminal lines capped at 1000 in React state.

- [ ] **Step 3: Active phase**

Pass active phase to `FlowMap` and `AgentCard`.

Visual:

- active node has bright ring.
- completed node has check icon.
- idle node has muted border.

- [ ] **Step 4: Verify with API status**

Manual:

1. Start dev server.
2. Open page.
3. Start a run with `template_a` and `maxCycles=1`.
4. Confirm terminal receives stdout.
5. Stop run if credentials are unavailable or the Agent waits on API.

Expected:

- UI does not freeze.
- Stop button remains usable.
- Errors are visible and recoverable.

### Task 9: 实现 Guided Demo 模式

**Files:**
- Create: `display/src/components/DemoCyclePlayer.tsx`
- Modify: `display/src/app/page.tsx`
- Modify: `display/src/app/page.module.css`

- [ ] **Step 1: Demo controls**

Demo player controls:

- play
- pause
- reset
- step forward
- mode label: `Guided Demo`

It must never call `/api/run`.

- [ ] **Step 2: Demo animation**

Every demo step:

- sets active phase
- appends a system terminal line prefixed `[demo]`
- highlights relevant Agent card
- updates a small “current handoff” panel

- [ ] **Step 3: Distinguish demo from real**

Use visible text:

```text
Guided Demo uses scripted sample events. Real Run starts AlphaCrafter through the ALPHACRAFTER Conda environment.
```

This text can be compact, but must be visible.

### Task 10: 实现 Agent 输出、指标和产物面板

**Files:**
- Create: `display/src/components/AgentActivityTimeline.tsx`
- Create: `display/src/components/AgentOutputPanel.tsx`
- Create: `display/src/components/MetricsPanel.tsx`
- Create: `display/src/components/ArtifactBrowser.tsx`
- Modify: `display/src/components/ConsoleClient.tsx`
- Modify: `display/src/app/page.module.css`

- [ ] **Step 1: Load logs/artifacts**

On selected session change and on process exit, fetch:

- `/api/logs?sessionId=${selectedSessionId}`
- `/api/artifacts?sessionId=${selectedSessionId}`

If no logs exist, show empty state with the exact session log path.

- [ ] **Step 2: AgentActivityTimeline**

`AgentActivityTimeline` props:

```ts
type AgentActivityTimelineProps = {
  activity: ParsedAgentActivity[];
  searchQuery: string;
};
```

Display:

- agent badge: Miner/Screener/Trader
- event label
- iteration number when present
- tool call chips when present
- cost when present
- error details when severity is `error`
- timestamp

Filtering:

- apply the global `searchQuery` against title, detail, tool names, and agent name
- if no activity is available, show the exact files being watched:
  - `logs/miner_agent.json`
  - `logs/screener_agent.json`
  - `logs/trader_agent.json`

This component is required for the user's requirement: "看到Agent在实际运行过程中进行的行为".

- [ ] **Step 3: AgentOutputPanel**

Tabs:

- Workflow
- Activity
- Miner
- Screener
- Trader

Workflow tab:

- cycle
- phase
- success
- timestamp
- collapsed output text

Agent tabs:

- event name
- success
- iteration
- tool call names
- tool argument preview
- total cost
- error detail
- timestamp
- output text

Long output:

- collapsed by default after 1200 chars
- expand/collapse button
- copy button
- search input that filters visible rows by event, output, tool names, and error detail

- [ ] **Step 4: MetricsPanel**

Show:

- net assets
- total assets
- available cash
- market value
- gross position
- net position
- Sharpe
- Max Drawdown
- Calmar
- return

Use small SVG sparklines for snapshot net assets when at least two points exist. If no points exist, show a text empty state.

- [ ] **Step 5: ArtifactBrowser**

Group by kind:

- Strategy
- Factors
- Account/Date
- Logs

Each artifact row:

- label
- relative path
- size
- updated time
- preview drawer
- copy preview button

No nested cards.

### Task 11: 完成响应式视觉和丰富动效

**Files:**
- Create: `display/src/lib/motion-system.ts`
- Modify: `display/src/app/globals.css`
- Modify: `display/src/app/page.module.css`
- Modify: `display/src/components/ConsoleClient.tsx`
- Modify: `display/src/components/HeroConsole.tsx`
- Modify: `display/src/components/AgentCard.tsx`
- Modify: `display/src/components/FlowMap.tsx`
- Modify: `display/src/components/DemoCyclePlayer.tsx`
- Modify: `display/src/components/AgentActivityTimeline.tsx`
- Modify: component CSS classes in existing components

- [ ] **Step 1: Create motion-system tokens**

`display/src/lib/motion-system.ts` must export shared motion tokens and variants:

```ts
import type { Variants } from "framer-motion";

export const motionTiming = {
  micro: 0.18,
  panel: 0.32,
  boot: 0.9,
};

export const motionEase = [0.16, 1, 0.3, 1] as const;

export const panelEnter: Variants = {
  hidden: { opacity: 0, y: 18, filter: "blur(6px)" },
  visible: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: motionTiming.panel, ease: motionEase },
  },
};

export const staggerDeck: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.07,
      delayChildren: 0.08,
    },
  },
};

export const terminalLineIn: Variants = {
  hidden: { opacity: 0, x: -8 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: motionTiming.micro, ease: motionEase },
  },
};

export const agentDock: Variants = {
  idle: { opacity: 0.72, scale: 0.985 },
  active: {
    opacity: 1,
    scale: 1,
    transition: { duration: motionTiming.micro, ease: motionEase },
  },
};
```

All framer-motion components must import variants from this file instead of declaring unrelated one-off timings.

- [ ] **Step 2: Implement signature motion**

Implement these motion moments:

- `ConsoleClient` boot sequence: use `staggerDeck` and `panelEnter`.
- `HeroConsole` first paint: background grid, status rail, agent dock, controls, terminal ready line appear in sequence.
- `FlowMap` phase transition: use SVG stroke dash or transform-driven data beam.
- `AgentCard` active state: use `agentDock`, tool chip pulse when related tool calls appear.
- `LiveTerminal` line insertion: use `terminalLineIn`.
- `AgentActivityTimeline` new event insertion: use `terminalLineIn` or a dedicated timeline variant.
- `DemoCyclePlayer`: every demo step drives the same active phase and handoff beam used by real run.

Do not implement random decorative bouncing, floating, or unrelated background particles.

- [ ] **Step 3: Desktop layout**

At `min-width: 1024px`:

- top dashboard uses two columns: visual flow left, controls right.
- below sections use a 12-column grid.
- terminal and output panels have stable height with internal scroll.

- [ ] **Step 4: Tablet layout**

At `768px <= width < 1024px`:

- hero stacks visual over controls.
- Agent cards remain three columns if width allows.
- logs and metrics stack.

- [ ] **Step 5: Mobile layout**

At `width < 768px`:

- single column.
- role cards become horizontal scroll with snap or stacked cards.
- terminal height max 50dvh.
- controls full width.
- no horizontal body scroll.

- [ ] **Step 6: Motion polish**

Add CSS keyframes:

- `phasePulse`
- `lineFlow`
- `panelEnter`
- `terminalLineIn`
- `scanlineSweep`
- `toolCallFlash`

Ensure all are disabled by the global `prefers-reduced-motion` rule.

- [ ] **Step 7: Anti-AI visual QA**

Before finalizing styles, inspect the page against this checklist:

- Does the first viewport clearly read as `AlphaCrafter` with three Agent roles, not a generic AI dashboard?
- Are Miner/Screener/Trader character assets visually central, not tiny decorative thumbnails?
- Are blue/gold/orange role colors used as system language, not random accents?
- Are there any purple/pink AI gradients, generic glass cards, stock orb backgrounds, or bland SaaS hero patterns? Remove them.
- Does motion explain boot, handoff, tool call, terminal stream, metrics settle, stop/failure/recovery?
- Is there a visible difference between Guided Demo and Real Run?

- [ ] **Step 8: Accessibility pass**

Check:

- all buttons have visible text or `aria-label`
- focus ring visible
- contrast readable
- no color-only status
- terminal has `aria-live="polite"` but does not steal focus

### Task 12: Playwright smoke test

**Files:**
- Create: `display/e2e/smoke.spec.ts`
- Modify: `display/playwright.config.ts`

- [ ] **Step 1: Configure Playwright**

Use webServer:

```ts
webServer: {
  command: "npm run dev",
  url: "http://127.0.0.1:3000",
  reuseExistingServer: !process.env.CI,
  timeout: 120_000
}
```

- [ ] **Step 2: Install Playwright Chromium**

Run:

```bash
cd display
npx playwright install chromium
```

Expected:

- Chromium browser for Playwright is installed or already present.

If this fails because network access is unavailable, do not replace Playwright with a browserless test. Report the failure and continue with `npm run build` plus manual browser QA once Chromium is available.

- [ ] **Step 3: Smoke test**

Test must verify:

- page title contains `AlphaCrafter`
- Miner/Screener/Trader visible
- session picker visible
- Guided Demo controls visible
- terminal visible
- no obvious horizontal overflow at 375px
- first viewport contains at least one `img` for each of the three character roles
- flow map exposes active phase state through visible text or `aria-current`
- page does not contain visible generic AI phrases: `AI-powered`, `revolutionary`, `unlock your potential`

Use two viewports:

- `{ width: 1440, height: 1000 }`
- `{ width: 375, height: 812 }`

- [ ] **Step 4: Run**

```bash
cd display
npm run test:e2e
```

Expected:

- Smoke tests pass.

- [ ] **Step 5: Reduced motion smoke**

Add a Playwright test using reduced motion:

```ts
test.use({ reducedMotion: "reduce" });
```

Verify:

- page still shows current run status text
- active phase is still visible by text/ring/class, not only animation
- no continuously animated element is required to understand state

### Task 13: 文档与最终验收

**Files:**
- Create: `display/README.md`
- Modify: root `README.md` only if user approves adding a link to `display/README.md`

- [ ] **Step 1: Write display README**

Must include:

- Purpose: local AlphaCrafter console.
- Prerequisites:
  - Node.js
  - npm
  - Conda env `ALPHACRAFTER`
- Start:

```bash
cd display
npm install
npm run dev
```

- Open:

```text
http://127.0.0.1:3000
```

- Real run behavior:

```text
The console starts AlphaCrafter with conda run --no-capture-output -n ALPHACRAFTER python -u main.py ...
```

- Safety:
  - local only
  - no Docker
  - no environment variables exposed to browser
  - only sandbox paths are readable

- [ ] **Step 2: Final verification commands**

Run:

```bash
cd display
npm run test
npm run build
npm run test:e2e
```

Also run:

```bash
conda run -n ALPHACRAFTER python --version
```

Expected:

- Python output is 3.10.x.
- Unit tests pass.
- Next build passes.
- Playwright smoke passes.

- [ ] **Step 3: Manual acceptance checklist**

Open `http://127.0.0.1:3000` and verify:

- Three provided character assets are visible.
- Visual style matches the assets: blue Miner, gold Screener, orange Trader.
- First viewport reads as a distinctive `Quant Lab / Agent Ops Deck`, not a generic AI SaaS dashboard.
- No purple/pink AI gradients, decorative blobs, generic glass-card stacks, stock AI copy, or tiny decorative-only character usage remain.
- Page explains actual AlphaCrafter flow.
- Guided Demo can play/pause/reset.
- Guided Demo visibly drives the same flow line, Agent active state, terminal stream, and activity timeline used by Real Run.
- Sessions list includes `template_a` and `template_us` if present.
- Real run can be started from a valid session.
- stdout/stderr appears in terminal.
- Agent activity timeline updates during a run and shows iteration/tool/error/cost details when present.
- Stop button sends termination and UI updates.
- Logs/artifacts refresh after run ends.
- Mobile 375px has no horizontal scroll.
- Reduced motion mode does not show continuous pulsing.
- Motion QA: boot sequence, Agent handoff beam, tool call pulse, terminal streaming, metrics settle, and stop/failure/completed recovery are all visible in normal motion mode.

---

## 8. MiniMax-M3 执行纪律

1. 每个任务开始前运行 `git status --short`。
2. 不要还原用户已有改动。
3. 不要删除 `display/picture/`。
4. 每完成一个任务，运行该任务指定验证命令。
5. 如果遇到 npm 网络失败，停止并报告，不要引入 CDN 脚本。
6. 如果真实 Agent 因缺少 API credentials 失败，这不是前端失败；前端必须显示错误并保持可恢复。
7. 如果 `conda run --no-capture-output` 在本机不可用，先验证 `conda run -n ALPHACRAFTER python -u main.py ...`，并把差异写进 `display/README.md`。
8. 不要把 `.env`、`config/models.json` 或 API key 内容打印到浏览器。
9. 视觉实现优先使用 CSS、SVG、lucide-react 和原始 PNG 素材；不要新增随机插画。
10. 保持组件文件聚焦；如果一个组件超过 260 行，拆分子组件。

---

## 9. 自检清单

### 9.1 需求覆盖

- 本地网页交互与展示：Task 1, 6, 7, 9, 10, 11。
- 使用 `ui-ux-pro-max` 的设计约束：视觉规划、动效、可访问性、响应式约束已写入第 4 节与 Task 11。
- 使用 `frontend-design` 的反 AI 味约束：第 4.0 节定义 `Quant Lab / Agent Ops Deck`，Task 11 增加 Anti-AI visual QA。
- 使用 picture 素材：Task 6 明确静态 import 六张图。
- 丰富且有意义的动效：第 4.4、4.4.1 节与 Task 11，包含 framer-motion motion system 与关键状态编排。
- 符合项目逻辑：第 0 节、API/log/parser 设计、Agent 元数据、真实流程图。
- 真实运行行为观测：Task 4, 5, 7, 8, 10。
- 不依赖 Docker、使用 `ALPHACRAFTER` 虚拟环境：第 3.1 节、Task 4、Task 13。
- Next.js 方案 3：第 2 节和所有 `src/app/api` 任务。

### 9.2 危险点检查

- 任意路径读取：已通过 `assertPathInside` 和白名单限制。
- Shell 注入：使用 `spawn` 数组参数，不拼 shell 字符串。
- 进程无法停止：SIGINT + SIGTERM 两阶段停止。
- 日志 JSON 损坏：parser 返回 warning，不让页面崩溃。
- HMR 状态丢失：页面可从日志重新加载历史状态。
- 凭据泄漏：health/API 不返回 env。

### 9.3 最终交付定义

完成后，用户应能执行：

```bash
cd display
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:3000
```

并在页面上完成：

- 看懂 AlphaCrafter 的三 Agent 闭环。
- 播放 Guided Demo。
- 选择本地 session。
- 用 `ALPHACRAFTER` Conda 环境启动真实运行。
- 查看运行中的 Agent 行为、日志、输出、指标和产物。
- 停止运行并恢复可操作状态。
