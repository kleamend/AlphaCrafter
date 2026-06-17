<h1 align="center">AlphaCrafter</h1>

<p align="center">
  <a href="https://arxiv.org/abs/2605.05580">
    <img src="https://img.shields.io/badge/ArXiv-2605.05580-b31b1b?style=for-the-badge">
  </a>

  <a href="#">
    <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge">
  </a>

  <a href="#">
    <img src="https://img.shields.io/badge/Python-3.10-3776AB?style=for-the-badge&logo=python&logoColor=white">
  </a>
</p>

**AlphaCrafter** 是一个面向横截面因子投资的多智能体框架。它把 **LLM 驱动的因子发现**、**风格感知的因子筛选**、**自适应执行** 三件事整合到同一条自动化流水线里。系统由三个专职 Agent 组成 —— **Miner（因子挖掘）**、**Screener（因子筛选）**、**Trader（策略执行）** —— 按日轮转运行，形成"假设 → 验证 → 执行"的闭环。

---

## 🧭 项目结构

```
AlphaCrafter/
├── alphacrafter/                # Python 端：多智能体框架主体
│   ├── agent/                   # Agent / 指令 / 工具 / 技能
│   │   ├── instructions/        # Miner / Screener / Trader / 市场通用 prompt
│   │   ├── openai/              # OpenAI 兼容 Agent 与通用 Agent 基类
│   │   ├── skills/              # 因子挖掘 / 筛选 / 策略注册 / 仓位管理 技能
│   │   └── toolkit/             # 文件 / Shell / 行情 / 回测 / 撮合 等工具
│   ├── sim/                     # A 股 / 美股 仿真撮合与账户 schema
│   ├── utils/                   # 评估、因子多样性等离线工具
│   └── main.py                  # 流水线主入口（Launcher）
├── display/                     # 本地 Next.js 显示控制台
│   ├── src/                     # 前端组件、API 路由、helper/hooks
│   ├── e2e/                     # Playwright 烟囱测试
│   ├── picture/                 # 三个 Agent 的角色素材
│   └── README.md                # 控制台使用说明
├── docs/                        # 设计与实现计划文档
├── DATA/                        # CSI300 / S&P500 示例数据
├── sandbox/                     # 会话（session）目录
├── docker-compose.yml           # 容器化一键启动
├── Dockerfile                   # 基础镜像
├── setup_env.sh / .bat          # 本地环境初始化脚本
└── README.md
```

---

## 🚀 快速开始

### 1. Docker Compose 一键启动

最简单的方式是用 Docker Compose，所有卷挂载都已在 `docker-compose.yml` 中配好。

```bash
# 后台启动容器
docker-compose up -d
```

### 2. 进入容器

```bash
# 在容器内开启交互式 bash
docker exec -it alphacrafter /bin/bash

# 切到源码目录
cd ./alphacrafter
```

### 3. 在 sandbox 中创建会话

AlphaCrafter 把每一次"流水线运行"隔离开来，存放在 sandbox 目录下。新建会话时，复制仓库自带的模板 `template_a`（A 股）或 `template_us`（美股）即可。复制完成后，按模板里的示例导入你的数据集并完成相关配置。

**目录结构参考：**

```bash
├── sandbox/
│   ├── gpt-5.3-backtest-csi300/    # 示例自定义会话
│   │   ├── config/
│   │   ├── logs/
│   │   ├── persistent/
│   │   │   ├── index_data/         # 000300.SH.csv
│   │   │   ├── stock_data/         # 000001.SH.csv, 000002.SH.csv, ...
│   │   │   ├── stock_financial_statements/  # 000001.SH.json, 000002.SH.json, ...
│   │   │   ├── stock_news/         # 000001.SH.json, 000002.SH.json, ...
│   │   │   ├── account.json
│   │   │   └── date.json
│   │   └── workspace/
```

### 4. 启动流水线

主入口是 `main.py`。在容器内进入 `alphacrafter` 目录后执行：

```bash
# 在容器内的 /alphacrafter 目录下
python main.py --session_id gpt-5.3-backtest-csi300 --resume (可选)
```

参数说明：

| 参数             | 必填 | 默认值 | 说明                              |
| ---------------- | ---- | ------ | --------------------------------- |
| `session_id`     | ✅   | —      | sandbox 下的会话目录名            |
| `--max-cycles`   | ❌   | `300`  | 最大循环次数                      |
| `--resume`       | ❌   | `False` | 是否从历史日志断点续跑           |

### 5. （可选）打开本地控制台

`display/` 目录里提供了一个 Next.js 本地控制台，可以更直观地观察一次真实的运行。详情参见 [display/README.md](display/README.md)。

---

## 🧠 三 Agent 协作循环

每一次 `cycle` 依次执行三个阶段：

```
Launcher
   │
   ▼
┌──────────┐    ┌──────────┐    ┌──────────┐
│  Miner   │ →  │ Screener │ →  │  Trader  │ →  account.json / date.json
└──────────┘    └──────────┘    └──────────┘
   挖掘 / 验证     风格评估          落策略 + step / backtest
   alpha 因子      选有效因子        自适应执行
   factors/*.json  factor ensemble   strategy.py
```

- **Miner**：在历史数据上挖掘 / 验证 alpha 因子，结果落到 `factors/*.json`。
- **Screener**：评估当前市场风格，从候选因子中挑选有效子集，组装成"因子集合（ensemble）"。
- **Trader**：把 ensemble 落成可执行的 `strategy.py`，并通过 `backtest` / `step` 工具进行验证与执行。

每个阶段都会把上一阶段的输出作为上下文（账户、日期、Agent 文本）注入到下一阶段，从而把"假设 → 验证 → 执行"串成一条闭环。

---

## 🛠 开发与验证

### Python 端

```bash
# 推荐：conda 环境隔离
conda create -n ALPHACRAFTER python=3.10 -y
conda activate ALPHACRAFTER
pip install -e .
```

### 显示控制台

```bash
cd display
npm install
npm run dev
# 浏览 http://127.0.0.1:3000
```

`display` 子项目的完整说明（环境准备、运行方式、安全边界、质量门禁、目录结构、首屏验收）见 [display/README.md](display/README.md)。

---

## 📄 引用

如果你在研究中使用了 AlphaCrafter，请引用我们的论文：

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

本项目基于 [MIT License](LICENSE) 开源。
