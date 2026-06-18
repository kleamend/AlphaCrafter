<h1 align="center">🧬 AlphaCrafter</h1>

<p align="center">
  <em>面向横截面因子投资的多智能体框架 · LLM 驱动的"假设 → 验证 → 执行"闭环</em>
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2605.05580">
    <img src="https://img.shields.io/badge/ArXiv-2605.05580-b31b1b?style=for-the-badge">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/Python-3.10-3776AB?style=for-the-badge&logo=python&logoColor=white">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/Next.js-15-000000?style=for-the-badge&logo=next.js&logoColor=white">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white">
  </a>
</p>

---

## ✨ 项目简介

**AlphaCrafter** 把"因子投资"完整地搬进了一条多智能体流水线 —— 由三位专职 Agent 协作完成日级别轮转:

| Agent | 角色 | 输出 |
|---|---|---|
| ⛏️ **Miner** | LLM 驱动的因子挖掘与验证 | `factors/*.json`(候选 alpha 因子) |
| 🔍 **Screener** | 风格感知的因子筛选与组合 | 因子集合(ensemble) |
| 📈 **Trader** | 自适应策略生成与执行 | `strategy.py` + 回测/撮合结果 |

Agent 通过共享 sandbox 会话、工具集(行情/财报/新闻/回测/撮合)与持久化账户串联,形成闭环。整套系统既能跑 A 股(CSI300),也能跑美股(S&P500),并附带一个本地 Next.js 控制台,实时观察每一轮的工具调用、阶段切换与产物。

---

## 🧭 项目结构

```
AlphaCrafter/
├── 🐍 alphacrafter/              # Python 端:多智能体框架主体
│   ├── agent/
│   │   ├── instructions/         # 🧾 Miner / Screener / Trader / 市场通用 prompt
│   │   │   ├── miner.py
│   │   │   ├── screener.py
│   │   │   ├── trader.py
│   │   │   ├── quantitative_trading_a.py    # 🇨🇳 A 股市场上下文
│   │   │   └── quantitative_trading_us.py   # 🇺🇸 美股市场上下文
│   │   ├── openai/               # 🤖 OpenAI 兼容 Agent / 通用 Agent 基类
│   │   ├── skills/               # 🛠️ 因子挖掘 / 筛选 / 策略注册 / 仓位管理 技能
│   │   │   ├── factor_mining.md
│   │   │   ├── factor_screening.md
│   │   │   ├── strategy_registration.md
│   │   │   ├── position_management.md
│   │   │   ├── quantitative_trading.md
│   │   │   ├── alpha158_documentation.md
│   │   │   └── example.md
│   │   └── toolkit/              # 🧰 工具集
│   │       ├── get_stock_data.py            # 📊 行情数据
│   │       ├── get_financial_statements.py  # 📄 财报
│   │       ├── get_news.py                  # 📰 新闻
│   │       ├── get_index_data.py            # 📉 指数
│   │       ├── search_factor.py             # 🔎 因子检索
│   │       ├── backtest.py                  # 🧪 回测
│   │       ├── step.py                      # ⏭️ 逐日撮合
│   │       ├── add_order.py / cancel_order.py
│   │       ├── read_file.py / write_file.py / shell.py
│   │       └── base.py
│   ├── sim/                      # ⚙️ A 股 / 美股 仿真撮合与账户 schema
│   │   ├── exchange_a.py
│   │   ├── exchange_us.py
│   │   ├── hook.py
│   │   ├── schemas/
│   │   └── utils/
│   ├── utils/                    # 📐 评估、因子多样性等离线工具
│   ├── sandbox/                  # 🏖️ 模板会话(template_a / template_us)
│   └── main.py                   # 🚀 流水线主入口(Launcher)
├── 🌐 display/                   # 本地 Next.js 显示控制台
│   ├── src/
│   │   ├── app/                  # Next 路由(含 SSE / artifacts / logs API)
│   │   ├── components/           # Topbar / HeroDeck / Workspace / AgentCard ...
│   │   ├── lib/                  # i18n / motion / hooks / schemas
│   │   └── test/                 # Vitest 单测
│   ├── e2e/                      # 🎭 Playwright 端到端烟囱测试
│   ├── picture/                  # 🎨 三位 Agent 的角色立绘 / 图标
│   └── README.md                 # 控制台使用说明
├── 📁 DATA/                      # CSI300 / S&P500 示例数据
├── 📚 docs/                      # 设计与实现计划
├── 🐳 Dockerfile                 # 基础镜像
├── 🐳 docker-compose.yml         # 一键起容器
├── 🧪 setup_env.sh / .bat        # 本地环境初始化脚本
├── 📦 setup.py / .env.example
└── 📖 README.md
```

---

## 🧠 三 Agent 协作循环

每一次 `cycle` 依次执行三个阶段,上一阶段的输出(账户 / 日期 / Agent 文本)作为上下文注入下一阶段:

```
       ┌───────────────────────────────────────────────┐
       │                  Launcher                     │
       │  alphacrafter/main.py · 调度 cycle 与上下文   │
       └───────────────────┬───────────────────────────┘
                           ▼
   ┌───────────┐     ┌───────────┐     ┌───────────┐
   │ ⛏️ Miner  │ ──▶ │ 🔍 Screener │ ──▶ │ 📈 Trader │ ──▶ account.json
   │           │     │           │     │           │     date.json
   │ 挖掘 alpha │     │ 风格评估   │     │ 策略生成    │
   │ 因子并验证 │     │ 因子集成   │     │ + step /   │
   │            │     │            │     │ backtest   │
   │ factors/   │     │ ensemble   │     │ strategy.py│
   │  *.json    │     │            │     │            │
   └───────────┘     └───────────┘     └───────────┘
```

- ⛏️ **Miner**:在历史数据上挖掘 / 验证 alpha 因子,结果落到 `factors/*.json`。
- 🔍 **Screener**:评估当前市场风格,从候选因子里挑选有效子集,组装成 ensemble。
- 📈 **Trader**:把 ensemble 落成可执行的 `strategy.py`,通过 `backtest` / `step` 工具完成验证与逐日撮合。

> 💡 三位 Agent 在同一个 sandbox 会话下共享文件系统、账户和日期,所以"想法 → 验证 → 决策 → 执行"完整地保留在一次运行的工作区里,可复跑、可断点续跑。

---

## 🚀 快速开始

### 方式 A · 🐳 Docker Compose 一键启动(推荐)

最简单的方式是用 Docker Compose,所有卷挂载都已在 `docker-compose.yml` 中配好:

```bash
# 后台启动容器
docker compose up -d

# 进入容器
docker exec -it alphacrafter /bin/bash

# 切到源码目录
cd /alphacrafter
```

### 方式 B · 🐍 本地 conda 环境

```bash
# 推荐:用 conda 隔离
conda create -n ALPHACRAFTER python=3.10 -y
conda activate ALPHACRAFTER

# 安装为可编辑包
pip install -e .

# 或者用脚本(Linux / macOS)
bash setup_env.sh

# Windows
setup_env.bat
```

并准备一个 `.env`(可参考 `.env.example`),填入你的 LLM 接入凭证。

### 🤖 当前默认模型:MiniMax-M3

AlphaCrafter 当前默认接入 [MiniMax-M3](https://platform.minimaxi.com/docs/guides/models-intro)(1M 上下文、原生 tool calling)。
走的是 **OpenAI Chat Completions 兼容端点**,因此无需额外的 SDK,直接用 `openai` Python 客户端即可。

`.env` 中只需配置两项:

```bash
API_URL=https://api.minimaxi.com/v1
API_KEY=<你的 MiniMax API Key>
```

> 想换其它 OpenAI 兼容端点(如 OpenAI 自身、Azure、其他第三方)?只需修改 `API_URL` /
> `API_KEY`,并在 `sandbox/<session>/config/models.json` 的 `models.json` 中增加对应模型条目
> 并设置 `producer` 字段(当前支持 `"OpenAI"` / `"MiniMax"`)。Launcher 会按 `producer`
> 路由到合适的 Agent 实现。

### 🧠 三个 Agent 实现 · 路由说明

`alphacrafter/agent/openai/` 下目前并存三种 Agent 实现,Launcher 会按模型配置中的
`producer` 字段选择:

| 文件 | 类 | 适用 producer | 协议 |
|---|---|---|---|
| `agent.py` | `Agent` | `"OpenAI"` | OpenAI Responses API(原生 `function_call`) |
| `chat_agent.py` | `ChatAgent` | `"OpenAI"` / `"MiniMax"` | OpenAI Chat Completions + 原生 `tool_calls` |
| `general_agent.py` | `Agent` (GeneralAgent) | 不支持原生工具调用的兜底 | Chat Completions + XML `<tool_call>` 解析 |

### 🧪 在 sandbox 中创建会话

AlphaCrafter 把每一次"流水线运行"隔离开来,存放在 `alphacrafter/sandbox/` 目录下。新建会话时,复制仓库自带的模板 `template_a`(A 股)或 `template_us`(美股),然后按模板里的示例导入你的数据集并完成相关配置。

**目录结构参考:**

```
alphacrafter/sandbox/
└── gpt-5.3-backtest-csi300/         # 自定义会话名
    ├── config/                      # 模型 / 市场 / 资金等配置
    ├── logs/                        # 三位 Agent 的实时日志
    ├── persistent/                  # 跨 cycle 保留的状态
    │   ├── index_data/              # 000300.SH.csv
    │   ├── stock_data/              # 000001.SH.csv, 000002.SH.csv, ...
    │   ├── stock_financial_statements/   # *.json
    │   ├── stock_news/              # *.json
    │   ├── account.json             # 账户(现金 / 持仓 / NAV)
    │   └── date.json                # 当前交易日
    └── workspace/                   # 当前 cycle 的临时产物(factors/ 等)
```

### ▶️ 启动流水线

主入口是 `alphacrafter/main.py`:

```bash
# 在容器或 conda 环境中,进入源码目录
cd alphacrafter

# 跑一次完整循环
python main.py --session_id gpt-5.3-backtest-csi300

# 或者断点续跑
python main.py --session_id gpt-5.3-backtest-csi300 --resume
```

**参数说明:**

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--session_id` | ✅ | — | sandbox 下的会话目录名 |
| `--max-cycles` | ❌ | `300` | 最大循环次数 |
| `--resume` | ❌ | `False` | 是否从历史日志断点续跑 |

---

## 🌐 本地控制台(display)

`display/` 是一个 Next.js 15 + React 19 的本地控制台,可以更直观地观察一次真实运行:

```bash
cd display
npm install
npm run dev
# 浏览 http://127.0.0.1:3000
```

### 控制台亮点

- 🧱 **三段式布局**:`Topbar`(产品标识 + 模式 / 语言切换)+ `HeroDeck`(状态栏 + 流程图 + 启停面板)+ `Workspace`(Agent 活动 / 输出 / 终端 / 指标 / 产物 多标签视图)。
- 📡 **SSE 实时事件流**:`/api/run/events` 把 Python 端的日志、状态、阶段切换推送给前端,断线自动重连。
- 🎬 **真实 / 引导演示双模式**:`Real Run` 启动真实 Python 进程,`Guided Demo` 用脚本化事件演示三位 Agent 的协作路径,无需后端。
- 🌍 **中英双语 i18n**:`zh` / `en` 一键切换,所有 UI 文案、Agent 简介、状态描述均已本地化。
- ♿ **无障碍支持**:状态栏的 ok / warn / down 同时通过颜色与形状(`CheckCircle2` / `TriangleAlert` / `XCircle`)表达,满足 WCAG 1.4.1;`prefers-reduced-motion` 下自动降级动效。
- 🧪 **质量门禁**:`npm run check` 串起 `lint + vitest + next build`,`npm run test:e2e` 跑 Playwright 烟囱测试。

> 详细的"环境准备 / 运行方式 / 安全边界 / 质量门禁 / 目录结构 / 首屏验收"请见 [display/README.md](display/README.md)。

---

## 🧰 工具与技能一览

### Agent 可调用的工具(toolkit)

| 类别 | 工具 | 用途 |
|---|---|---|
| 📊 数据 | `get_stock_data` / `get_index_data` | 拉取股票 K 线与指数行情 |
| 📄 基本面 | `get_financial_statements` | 财务报表 |
| 📰 信息流 | `get_news` | 股票相关新闻 |
| 🔎 检索 | `search_factor` | 搜索已落库的 alpha 因子 |
| 🧪 回测 | `backtest` | 离线回测 |
| ⏭️ 撮合 | `step` / `add_order` / `cancel_order` | 单日逐步撮合与下单 / 撤单 |
| 📁 文件 | `read_file` / `write_file` | 工作区读写 |
| 💻 Shell | `shell` | 受控命令执行 |

### Skills(任务说明书)

- ⛏️ `factor_mining.md` — 因子挖掘指南
- 🔍 `factor_screening.md` — 因子筛选指南
- 📋 `strategy_registration.md` — 策略注册流程
- 📈 `position_management.md` — 仓位管理
- 💹 `quantitative_trading.md` — 量化交易整体范式
- 📚 `alpha158_documentation.md` — Alpha158 因子库参考
- 📝 `example.md` — 端到端示例

---

## 🛠️ 开发与验证

### Python 端

```bash
conda activate ALPHACRAFTER

# 运行一次完整 cycle 做验证
cd alphacrafter
python main.py --session_id <你的会话> --max-cycles 1
```

### 前端控制台

```bash
cd display

# 一次性跑完 lint + 单测 + 生产构建
npm run check

# 端到端烟囱测试
npm run test:e2e
```

---

## 📦 数据集

`DATA/` 目录提供了开箱即用的示例数据:

- 🇨🇳 `stock_data_CSI300/` — 沪深 300 成分股
- 🇺🇸 `stock_data_S&P500/` — 标普 500 成分股

将其按 `sandbox/<session>/persistent/stock_data/` 的格式导入即可开跑。

---

## 📄 引用

如果你在研究中使用了 AlphaCrafter,请引用我们的论文:

```bibtex
@misc{yuan2026alphacrafterfullstackmultiagentframework,
      title={AlphaCrafter: A Full-Stack Multi-Agent Framework for Cross-Sectional Quantitative Trading},
      author={Yishuo Yuan and Jiayi Sheng and Sirui Zeng and Jiaqi Wang and Jiaheng Liu},
      year={2026},
      eprint={2605.05580},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2605.05580},
}
```

---

## 📝 许可证

本项目基于 [MIT License](LICENSE) 开源。欢迎 🌟 Star、🍴 Fork、🐛 Issue、🔧 PR。
