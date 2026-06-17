# AlphaCrafter 显示控制台（Display Console）

`display/` 是一个 **本地运行** 的 Next.js 应用，用来在浏览器里观察和驱动 `alphacrafter/` 多智能体流水线。它**不**对外网开放、**不**部署到生产环境、也**不**替代 Python CLI —— 它的定位是：单次运行、本机操作员视角的运维面板。

## 功能概览

控制台主要由以下几块组成：

- **Quant Lab / Agent Ops Deck 主页（Hero）**：展示蓝、金、橙三色角色（**Miner / Screener / Trader**），并用一条与真实流水线一致的流向线串起 Miner → Screener → Trader → 反馈到 Miner。
- **Guided Demo（引导式演示）**：在不触碰 sandbox 的前提下，复刻真实运行的阶段切换、终端输出和活动时间线，方便用户快速理解流水线。
- **Real Run（真实运行）**：通过本机的 `ALPHACRAFTER` conda 环境拉起 Python 流水线，把 stdout / stderr、阶段切换、工具调用和运行指标实时回传 UI。
- **Sessions 选择器**：列出 `alphacrafter/sandbox/` 下所有合法 session，包含仓库自带的 `template_a` / `template_us`。
- **Logs / Artifacts 面板**：运行结束后自动刷新，展示产物与日志。

## 环境准备

控制台依赖尽可能精简，只需准备：

- **Node.js**（推荐 18+，适配 Next.js 15）和 **npm**。
- **Conda** 中存在名为 `ALPHACRAFTER` 的环境，且已安装好 `alphacrafter` 包（一次性安装步骤见仓库根目录的 `README.md` 与 `setup_env.sh`）。
- `display/picture/` 下的 **六张角色 PNG**（已纳入版本管理）。

不需要 Docker、不需要云端凭据，也不会把任何环境变量暴露给浏览器。

## 安装与启动

在仓库根目录执行：

```bash
cd display
npm install
npm run dev
```

随后在浏览器中打开：

```
http://127.0.0.1:3000
```

dev server **只** 绑定 `127.0.0.1:3000`，设计上不接受来自局域网的访问。

## 真实运行的启动方式

当你在合法 session 上点击 **Start** 时，控制台会在后端执行：

```bash
conda run --no-capture-output -n ALPHACRAFTER \
  python -u main.py <sessionId> --max-cycles <N> [--resume]
```

`cwd` 固定为仓库内的 `alphacrafter/`，控制台会：

- **逐行** 抓取 stdout / stderr 并推送到 LiveTerminal。
- 监听 `MINER PHASE` / `SCREENER PHASE` / `TRADER PHASE` / `CYCLE: n` 标记，驱动 FlowMap 与 AgentActivityTimeline。
- 点击 **Stop** 时向整个进程组发送 `SIGINT`；如果 8 秒内未退出，回退到 `SIGTERM`。
- 暴露退出码、信号、迭代次数、最近一次工具调用以及错误信息。

## 安全边界

- **仅本机**：dev server 绑定 `127.0.0.1`，不向主机外暴露任何端口。
- **不依赖 Docker**：控制台通过 `conda run` 直接驱动 Python 流水线，**不**使用 Docker / docker-compose 或其他容器运行时。
- **环境变量不出浏览器**：进程管理全部在服务端完成，浏览器只能看到 SSE 事件流。`OPENAI_API_KEY` 等敏感变量只存在于 `ALPHACRAFTER` conda 进程内。
- **路径沙箱化**：文件与产物接口统一通过 `display/src/lib/repo-paths.ts` 解析路径，并拒绝任何逃逸出 `alphacrafter/sandbox/<sessionId>/` 的请求。日志与产物只能读取 SessionPicker 中列出的 session。

## 质量门禁

在 `display/` 目录下：

```bash
npm run test        # Vitest 单元测试
npm run build       # Next.js 生产构建
npm run test:e2e    # Playwright 烟囱测试（桌面 + 移动端 + reduced motion）
npm run check       # lint + test + build 一站式检查
```

Python 侧要求 `3.10.x`：

```bash
conda run -n ALPHACRAFTER python --version
```

## display 目录结构

- `src/app/` — Next.js App Router 入口、全局 CSS 与 `/api/{run,sessions,logs,artifacts,health}` 路由。
- `src/components/` — 一块面板对应一个小组件，单一职责。
- `src/lib/` — 服务端帮助模块：进程管理、session 存储、产物读取、日志解析、环境检查、动画系统、参数校验。
- `src/test/` — 服务端模块的 Vitest 单元测试。
- `e2e/` — Playwright 烟囱测试。
- `picture/` — 六张角色 PNG（**不要修改**，这是唯一的官方素材）。

## 首屏体验验收标准

- 三张角色卡必须在首屏可见，且配色与身份完全对应（Miner = 蓝、Screener = 金、Trader = 橙）。
- 流向线必须读作 **Miner → Screener → Trader → 反馈到 Miner**，**不**接受通用流水线条。
- Hero 文案必须描述 AlphaCrafter 真实循环（因子挖掘、风格感知筛选、策略编译、执行反馈），**不**使用通用 AI 营销话术、紫色/粉色渐变、装饰性色块或玻璃卡片堆叠。
- **Guided Demo** 真实可操作：**Play / Pause / Reset** 必须驱动与 Real Run 一致的阶段切换、终端流和活动时间线。

如果以上任一不满足，按回归处理。
