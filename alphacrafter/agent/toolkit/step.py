"""
仿真步进工具（StepTool）

功能概述：
    让 Agent 在"仿真时钟"中推进 N 个交易日，并触发完整的
    Exchange.pre_tick -> Hook.on_tick -> Exchange.post_tick 流程。
    每次推进都会更新账户状态、订单状态、日终快照等。

数据流（每日循环）：
    ┌──────────────┐   pre_tick   ┌──────────┐   on_tick   ┌────────┐
    │  Exchange    │ ──────────→ │  Hook    │ ─────────→ │ 策略  │
    │  (撮合/行情) │              │ (钩子)   │             │       │
    └──────────────┘              └──────────┘             └───────┘
           │                                                    │
           │ ←────────────── post_tick（撮合/结算）──────────────┘
           ▼
    ┌──────────────┐
    │  account.json│
    │  date.json   │
    │  snapshot.log│
    └──────────────┘

设计要点：
    - mode='a' (A 股) 与 mode='us' (美股) 走不同的 Exchange 实现。
    - 每个交易日都会落一次"账户快照"到 snapshot.json，结束时
      用这些快照计算组合的绩效指标。
    - 自动在 steps<5 时上调为 5，避免"只推一两天"导致的样本不足。
"""

from typing import Dict, Any, Callable, List
import json
import os
from time import sleep
from pathlib import Path
from datetime import datetime
import numpy as np

from .base import BaseTool
from alphacrafter.sim.hook import Hook


class StepTool(BaseTool):
    """推进仿真时钟并触发策略钩子的工具。"""

    def __init__(
        self,
        date_file_path: str = "../persistent/date.json",
        dataset_dir_path: str = "../persistent/stock_data",
        account_file_path: str = "../persistent/account.json",
        strategy_file_path: str = "./strategy.py",
        log_file_path: str = "../logs/snapshot.json",
        mode: str = "a",
    ):
        """初始化 StepTool。

        参数:
            date_file_path:    当前日期 JSON 文件。
            dataset_dir_path:  股票数据目录。
            account_file_path: 账户 JSON 文件。
            strategy_file_path:策略入口文件（由 Hook 加载）。
            log_file_path:     快照日志文件。
            mode:              'a'（A 股）或 'us'（美股）。
        """
        self.date_file_path = date_file_path
        self.dataset_dir_path = dataset_dir_path
        self.account_file_path = account_file_path
        self.strategy_file_path = strategy_file_path
        self.log_file_path = log_file_path
        self.mode = mode.lower()

        # ── 按市场类型选择 Exchange 实现 ──
        if self.mode == "a":
            from alphacrafter.sim.exchange_a import Exchange
        elif self.mode == "us":
            from alphacrafter.sim.exchange_us import Exchange
        else:
            raise ValueError(
                f"Unsupported mode: {mode}. Supported modes: 'a' (A-share), 'us' (US stock)"
            )

        # Exchange 与 Hook 是 step 流程的核心驱动者
        self.exchange = Exchange(dataset_dir_path, account_file_path, date_file_path)
        self.hook = Hook(strategy_file_path)

        # 日志与快照相关
        Path(self.log_file_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_snapshot_file()
        self.step_snapshots = []  # 当前 run 累积的快照（用于指标计算）

    # ── 初始化与持久化辅助 ───────────────────────────

    def _init_snapshot_file(self) -> None:
        """如果快照日志不存在则初始化为空数组。"""
        if not os.path.exists(self.log_file_path):
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                json.dump([], f, indent=2, ensure_ascii=False)

    def _read_date_file(self) -> Dict[str, any]:
        """读取 date.json 并校验必要字段。"""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if 'current_date' not in data:
            raise ValueError("date.json missing 'current_date' field")
        if 'trading_days' not in data:
            raise ValueError("date.json missing 'trading_days' field")
        return data

    def _write_date_file(self, data: Dict[str, any]) -> None:
        """将 date 数据写回。"""
        Path(self.date_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.date_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _read_account_file(self) -> str:
        """读取 account.json 的原始字符串。"""
        if not os.path.exists(self.account_file_path):
            return "{}"
        with open(self.account_file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _log_account_snapshot(self, date: str) -> None:
        """记录一份账户快照到 snapshot.json，同时保留到内存用于指标计算。

        为了避免策略细节泄露到 LLM 上下文，会在快照中重置 watch_list / orders / positions。
        """
        try:
            account_data = self._read_account_file()
            account_dict = json.loads(account_data) if account_data != "{}" else {}
            account_dict["watch_list"] = []
            account_dict["orders"] = []
            account_dict["positions"] = []

            snapshot = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "current_date": date,
                "account": account_dict,
            }

            # 内存中保留少量关键指标（用于绩效计算）
            self.step_snapshots.append({
                "date": date,
                "net_assets": account_dict.get("net_assets", 0.0),
                "total_assets": account_dict.get("total_assets", 0.0),
                "available_cash": account_dict.get("available_cash", 0.0),
                "market_value": account_dict.get("market_value", 0.0),
                "gross_position_rate": account_dict.get("gross_position_rate", 0.0),
                "net_position_rate": account_dict.get("net_position_rate", 0.0),
            })

            # 追加到 snapshot.json
            if os.path.exists(self.log_file_path):
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    snapshots = json.load(f)
            else:
                snapshots = []
            snapshots.append(snapshot)
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                json.dump(snapshots, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"Warning: Failed to log account snapshot: {e}")

    # ── 绩效指标计算 ───────────────────────────

    def _calculate_metrics(self) -> Dict[str, float]:
        """根据 step_snapshots 计算组合绩效指标。

        关键约定：
          - A 股按 240 个交易日/年做年化
          - 无风险利率 = 0.16%（约 1.6% 年化）
          - Sharpe = 平均超额收益 / 波动率 * sqrt(240)
          - MaxDrawdown = 任意历史峰值到当前值的最大回撤
        """
        if len(self.step_snapshots) < 2:
            return {k: 0.0 for k in [
                "Period Return (%)", "Annualized Return (%)", "Sharpe Ratio",
                "Max Drawdown (%)", "Calmar Ratio",
                "Average Gross Position Rate (%)", "Average Net Position Rate (%)",
            ]}

        net_assets = [s["net_assets"] for s in self.step_snapshots]
        gross_position_rates = [s.get("gross_position_rate", 0.0) for s in self.step_snapshots]
        net_position_rates = [s.get("net_position_rate", 0.0) for s in self.step_snapshots]

        # 日收益率 = (今日 - 昨日) / 昨日
        daily_returns = []
        for i in range(1, len(net_assets)):
            if net_assets[i - 1] > 0:
                daily_returns.append((net_assets[i] - net_assets[i - 1]) / net_assets[i - 1])
            else:
                daily_returns.append(0.0)

        if not daily_returns:
            return {k: 0.0 for k in [
                "Period Return (%)", "Annualized Return (%)", "Sharpe Ratio",
                "Max Drawdown (%)", "Calmar Ratio",
                "Average Gross Position Rate (%)", "Average Net Position Rate (%)",
            ]}

        total_days = len(daily_returns)
        total_years = total_days / 240

        # 期间收益率与年化收益率
        initial_net_assets = net_assets[0]
        final_net_assets = net_assets[-1]
        period_return = (
            (final_net_assets - initial_net_assets) / initial_net_assets
            if initial_net_assets > 0 else 0.0
        )
        annualized_return = (
            (1 + period_return) ** (1 / total_years) - 1
            if total_years > 0 and initial_net_assets > 0 else 0.0
        )

        # Sharpe
        risk_free_rate = 0.0016
        daily_risk_free = risk_free_rate / 240
        excess_returns = [r - daily_risk_free for r in daily_returns]
        avg_excess = np.mean(excess_returns) if excess_returns else 0.0
        std_excess = np.std(excess_returns) if len(excess_returns) > 1 else 1e-6
        sharpe = (avg_excess / std_excess) * np.sqrt(240) if std_excess > 0 else 0.0

        # Max Drawdown
        peak = net_assets[0]
        max_dd = 0.0
        for v in net_assets:
            if v > peak:
                peak = v
            if peak > 0:
                dd = (peak - v) / peak
                if dd > max_dd:
                    max_dd = dd

        calmar = annualized_return / max_dd if max_dd > 0 else 0.0

        return {
            "Period Return (%)": round(period_return * 100, 2),
            "Annualized Return (%)": round(annualized_return * 100, 2),
            "Sharpe Ratio": round(sharpe, 2),
            "Max Drawdown (%)": round(max_dd * 100, 2),
            "Calmar Ratio": round(calmar, 2),
            "Average Gross Position Rate (%)": round(np.mean(gross_position_rates) * 100, 2),
            "Average Net Position Rate (%)": round(np.mean(net_position_rates) * 100, 2),
        }

    # ── 日期辅助 ───────────────────────────

    def _find_next_trading_day(self, current_date: str, trading_days: List[str], steps: int) -> str:
        """在 trading_days 列表中向前推进 steps 步。

        若越过末端则返回最后一个交易日（仿真终点）。
        """
        try:
            current_idx = trading_days.index(current_date)
            next_idx = current_idx + steps
            if next_idx >= len(trading_days):
                return trading_days[-1]
            return trading_days[next_idx]
        except ValueError as e:
            if "not in list" in str(e):
                raise ValueError(f"Current date {current_date} not found in trading days list")
            raise e

    def _order_results_to_string(self, results: List) -> str:
        """将 OrderResultSchema 列表转成多行字符串。"""
        if not results:
            return ""
        lines = []
        for result in results:
            timestamp = result.timestamp
            if hasattr(timestamp, 'strftime'):
                timestamp = timestamp.strftime('%Y-%m-%d')
            result_lines = [
                f"order_id: {result.order_id}",
                f"symbol: {result.symbol}",
                f"order_type: {result.order_type}",
                f"status: {result.status}",
            ]
            if result.message:
                result_lines.append(f"message: {result.message}")
            lines.append("\n".join(result_lines))
        return "\n\n".join(lines)

    # ── 工具实现工厂 ───────────────────────────

    def get_implementation(self) -> Callable:
        def step(days: int) -> str:
            """推进仿真 N 个交易日。

            参数:
                days: 推进的交易日数（小于 5 时会被自动提升为 5）。

            返回值:
                推进结果 + 绩效指标的多行文本。
            """
            try:
                # 防止样本过少，至少跑 5 天
                if days < 5:
                    days = 5
                    print(f"Starting step execution for {days} trading days...")

                # 清空本轮快照
                self.step_snapshots = []

                # 读取初始日期与交易日序列
                date_data = self._read_date_file()
                current_date_str = date_data['current_date']
                trading_days = date_data['trading_days']

                all_results = []
                next_date_str = current_date_str

                # 记录"起点"快照
                initial_account = self._read_account_file()
                account_dict = json.loads(initial_account) if initial_account != "{}" else {}
                self.step_snapshots.append({
                    "date": current_date_str,
                    "net_assets": account_dict.get("net_assets", 0.0),
                    "total_assets": account_dict.get("total_assets", 0.0),
                    "available_cash": account_dict.get("available_cash", 0.0),
                    "market_value": account_dict.get("market_value", 0.0),
                    "gross_position_rate": account_dict.get("gross_position_rate", 0.0),
                    "net_position_rate": account_dict.get("net_position_rate", 0.0),
                })

                # ── 逐日推进仿真时钟 ──
                for i in range(days):
                    print(f"Processing day {i+1}/{days}...")
                    print(f"  Processing exchange pretick...")
                    self.exchange.pre_tick()
                    print(f"  ✓ Exchange pre tick processed")
                    sleep(0.4)

                    print(f"  Executing strategy hook...")
                    self.hook.on_tick()
                    print(f"  ✓ Strategy hook executed")
                    sleep(0.4)

                    print(f"  Processing exchange tick...")
                    results = self.exchange.post_tick()
                    print(f"  ✓ Exchange post tick processed")
                    sleep(0.4)

                    # 记录当日"终态"快照
                    self._log_account_snapshot(next_date_str)
                    print(f"  ✓ Account snapshot logged")

                    day_result = {"date": next_date_str, "results": results}
                    all_results.append(day_result)

                    # 计算下一个交易日并落盘
                    next_date_str = self._find_next_trading_day(next_date_str, trading_days, 1)
                    print(f"  Next trading day: {next_date_str}")
                    date_data['current_date'] = next_date_str
                    self._write_date_file(date_data)
                    print(f"  ✓ Date file updated")
                    sleep(0.4)

                    print(f"  Day {i+1} completed\n")

                # 计算并组装输出
                metrics = self._calculate_metrics()
                output_lines = [f"Advanced {days} trading days: {current_date_str} → {next_date_str}"]

                if metrics.get("Period Return (%)", 0.0) != 0.0 or any(
                    v != 0.0 for k, v in metrics.items() if "Position Rate" not in k
                ):
                    output_lines.append("")
                    output_lines.append("📊 Performance Metrics:")
                    for name, value in metrics.items():
                        output_lines.append(f"  {name}: {value}")
                else:
                    output_lines.append("")
                    output_lines.append("No orders executed during this step.")

                return "\n".join(output_lines)

            except Exception as e:
                import traceback
                return f"Error during step execution: {str(e)}\n{traceback.format_exc()}"

        return step

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    "Advance the simulation by N trading days using the strategy defined in "
                    "`workspace/strategy.py`. Returns performance metrics (Period Return, "
                    "Annualized Return, Sharpe Ratio, Max Drawdown, Calmar Ratio, Average "
                    "Position Rates), execution results, and account state."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of trading days to advance",
                            "minimum": 5,
                            "maximum": 10,
                        }
                    },
                    "required": ["days"],
                },
            }
        raise ValueError(f"Unsupported producer: {producer}")
