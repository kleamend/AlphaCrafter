"""
回测工具（BacktestTool）

功能概述：
    让 Agent 对一个已有策略进行"回放式"评估：从 N 天前开始，
    一日日推进仿真时钟，直到当前日期，然后计算绩效指标。

与 StepTool 的核心区别：
    - StepTool 是"实盘推进"，会改写真实的 date.json / account.json；
    - BacktestTool 是"沙箱回放"，进入时保存原始状态，结束时强制还原，
      不会对真实账户造成任何影响。

数据流：
    ┌──────────────┐
    │ 保存原始状态  │ (date.json / account.json)
    └──────┬───────┘
           ▼
    ┌──────────────┐  for day in N:
    │ 推进 N 个交易日  │  pre_tick → on_tick → post_tick → 落快照
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │ 计算绩效指标  │ (Sharpe / MaxDD / Calmar ...)
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │ 还原原始状态  │ (finally: 必执行)
    └──────────────┘
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


class BacktestTool(BaseTool):
    """在历史数据上回放策略的回测工具。"""

    def __init__(
        self,
        date_file_path: str = "../persistent/date.json",
        account_file_path: str = "../persistent/account.json",
        dataset_dir_path: str = "../persistent/stock_data",
        strategy_file_path: str = "./strategy.py",
        log_file_path: str = "../logs/backtest_results.json",
        mode: str = "a",
    ):
        """初始化 BacktestTool。

        参数:
            date_file_path:    当前日期 JSON 文件（回测过程中会被临时改写）。
            account_file_path: 账户 JSON 文件（同上）。
            dataset_dir_path:  股票数据目录。
            strategy_file_path:策略入口文件。
            log_file_path:     回测结果日志。
            mode:              'a'（A 股）或 'us'（美股）。
        """
        self.date_file_path = date_file_path
        self.account_file_path = account_file_path
        self.dataset_dir_path = dataset_dir_path
        self.strategy_file_path = strategy_file_path
        self.log_file_path = log_file_path
        self.mode = mode.lower()

        # 选市场
        if self.mode == "a":
            from alphacrafter.sim.exchange_a import Exchange
        elif self.mode == "us":
            from alphacrafter.sim.exchange_us import Exchange
        else:
            raise ValueError(
                f"Unsupported mode: {mode}. Supported modes: 'a' (A-share), 'us' (US stock)"
            )

        # 用于在回测结束/异常后还原"真实"状态
        self.original_date_data = None
        self.original_account_data = None
        self.exchange = Exchange(dataset_dir_path, account_file_path, date_file_path)
        self.hook = Hook(strategy_file_path)
        self.backtest_snapshots = []  # 本次回测的账户快照

    def get_name(self) -> str:
        """工具注册名。"""
        return "backtest"

    # ── 持久化辅助 ───────────────────────────

    def _read_date_file(self, file_path: str) -> Dict[str, any]:
        """读取并校验 date.json。"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Date file not found: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if 'current_date' not in data:
            raise ValueError(f"date.json missing 'current_date' field")
        if 'trading_days' not in data:
            raise ValueError(f"date.json missing 'trading_days' field")
        return data

    def _write_date_file(self, data: Dict[str, any], file_path: str) -> None:
        """写入 date.json。"""
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _read_account_file(self, file_path: str) -> Dict[str, any]:
        """读取账户文件，不存在时返回默认账户（1000 万初始资金）。"""
        if not os.path.exists(file_path):
            return {
                "total_assets": 10000000.0,
                "net_assets": 10000000.0,
                "available_cash": 10000000.0,
                "market_value": 0.0,
                "total_profit_loss": 0.0,
                "total_profit_loss_rate": 0.0,
                "gross_position_rate": 0.0,
                "net_position_rate": 0.0,
                "positions": [],
                "orders": [],
                "watch_list": [],
            }
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_account_file(self, data: Dict[str, any], file_path: str) -> None:
        """写入账户文件。"""
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ── 状态保存与还原 ───────────────────────────

    def _save_original_state(self) -> None:
        """进入回测前：备份原始 date 与 account。"""
        self.original_date_data = (
            self._read_date_file(self.date_file_path)
            if os.path.exists(self.date_file_path) else None
        )
        self.original_account_data = (
            self._read_account_file(self.account_file_path)
            if os.path.exists(self.account_file_path) else None
        )

    def _restore_original_state(self) -> None:
        """回测结束/异常：恢复进入前的状态。

        - 如果原来存在 -> 写回
        - 如果原来不存在但被创建过 -> 删除
        """
        if self.original_date_data is not None:
            self._write_date_file(self.original_date_data, self.date_file_path)
        elif os.path.exists(self.date_file_path):
            os.remove(self.date_file_path)

        if self.original_account_data is not None:
            self._write_account_file(self.original_account_data, self.account_file_path)
        elif os.path.exists(self.account_file_path):
            os.remove(self.account_file_path)

    def _log_account_snapshot(self, date: str, account_data: Dict[str, any]) -> None:
        """在内存中追加一份快照（仅保留少量关键指标）。"""
        try:
            snapshot = {
                "date": date,
                "net_assets": account_data.get("net_assets", 0.0),
                "total_assets": account_data.get("total_assets", 0.0),
                "available_cash": account_data.get("available_cash", 0.0),
                "market_value": account_data.get("market_value", 0.0),
                "gross_position_rate": account_data.get("gross_position_rate", 0.0),
                "net_position_rate": account_data.get("net_position_rate", 0.0),
            }
            self.backtest_snapshots.append(snapshot)
        except Exception as e:
            print(f"Warning: Failed to log account snapshot: {e}")

    def _find_past_trading_day(self, current_date: str, trading_days: List[str], days_ago: int) -> str:
        """查找过去第 N 个交易日。索引越界则返回首/尾交易日。"""
        try:
            current_idx = trading_days.index(current_date)
            target_idx = current_idx - days_ago
            if target_idx < 0:
                return trading_days[0]
            elif target_idx >= len(trading_days):
                return trading_days[-1]
            return trading_days[target_idx]
        except ValueError as e:
            if "not in list" in str(e):
                raise ValueError(f"Current date {current_date} not found in trading days list")
            raise e

    # ── 绩效指标计算 ───────────────────────────

    def _calculate_metrics(self) -> Dict[str, float]:
        """按净值序列计算回测绩效。

        关键约定：
          - 交易日按 252 天/年做年化
          - 无风险利率 0.16%（年化）
        """
        if len(self.backtest_snapshots) < 2:
            return {k: 0.0 for k in [
                "Total Return (%)", "Annualized Return (%)", "Sharpe Ratio",
                "Max Drawdown (%)", "Calmar Ratio",
                "Average Gross Position Rate (%)", "Average Net Position Rate (%)",
            ]}

        net_assets = [s["net_assets"] for s in self.backtest_snapshots]
        gross_position_rates = [s.get("gross_position_rate", 0.0) for s in self.backtest_snapshots]
        net_position_rates = [s.get("net_position_rate", 0.0) for s in self.backtest_snapshots]

        daily_returns = []
        for i in range(1, len(net_assets)):
            if net_assets[i - 1] > 0:
                daily_returns.append((net_assets[i] - net_assets[i - 1]) / net_assets[i - 1])
            else:
                daily_returns.append(0.0)

        if not daily_returns:
            return {k: 0.0 for k in [
                "Total Return (%)", "Annualized Return (%)", "Sharpe Ratio",
                "Max Drawdown (%)", "Calmar Ratio",
                "Average Gross Position Rate (%)", "Average Net Position Rate (%)",
            ]}

        total_days = len(daily_returns)
        total_years = total_days / 252

        # 总收益 & 年化收益
        initial_net_assets = net_assets[0]
        final_net_assets = net_assets[-1]
        total_return = (
            (final_net_assets - initial_net_assets) / initial_net_assets
            if initial_net_assets > 0 else 0.0
        )
        annualized_return = (
            (1 + total_return) ** (1 / total_years) - 1
            if total_years > 0 and initial_net_assets > 0 else 0.0
        )

        # Sharpe
        risk_free_rate = 0.0016
        daily_risk_free = risk_free_rate / 252
        excess_returns = [r - daily_risk_free for r in daily_returns]
        avg_excess = np.mean(excess_returns) if excess_returns else 0.0
        std_excess = np.std(excess_returns) if len(excess_returns) > 1 else 1e-6
        sharpe = (avg_excess / std_excess) * np.sqrt(252) if std_excess > 0 else 0.0

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
            "Total Return (%)": round(total_return * 100, 2),
            "Annualized Return (%)": round(annualized_return * 100, 2),
            "Sharpe Ratio": round(sharpe, 2),
            "Max Drawdown (%)": round(max_dd * 100, 2),
            "Calmar Ratio": round(calmar, 2),
            "Average Gross Position Rate (%)": round(np.mean(gross_position_rates) * 100, 2),
            "Average Net Position Rate (%)": round(np.mean(net_position_rates) * 100, 2),
        }

    def _log_results(self, backtest_result: Dict[str, any]) -> None:
        """把本次回测结果（带时间戳）追加到日志文件。"""
        try:
            if os.path.exists(self.log_file_path):
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            else:
                logs = []
            backtest_result["timestamp"] = datetime.now().isoformat()
            logs.append(backtest_result)
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to log backtest results: {e}")

    # ── 工具实现工厂 ───────────────────────────

    def get_implementation(self) -> Callable:
        def backtest(days: int) -> str:
            """对策略执行 N 个交易日的回测。

            参数:
                days: 回测窗口长度（<= 120，超过会被截断为 120）。

            返回值:
                性能指标的多行文本（Total Return / Sharpe / MaxDD / Calmar 等）。
            """
            backtest_result = {"status": "success", "days": days, "error": None}
            self.backtest_snapshots = []

            try:
                # ── 入参校验 ──
                if days <= 0:
                    error_msg = f"Error: days must be positive, got {days}"
                    backtest_result["status"] = "failed"
                    backtest_result["error"] = error_msg
                    self._log_results(backtest_result)
                    return error_msg

                if days >= 120:
                    days = 120  # 上限保护，避免长回测拖慢 Agent

                # ── 备份原始状态并设置回测窗口 ──
                self._save_original_state()
                date_data = self._read_date_file(self.date_file_path)
                current_date_str = date_data['current_date']
                trading_days = date_data['trading_days']

                past_date_str = self._find_past_trading_day(current_date_str, trading_days, days)
                temp_date_data = {"current_date": past_date_str, "trading_days": trading_days}
                self._write_date_file(temp_date_data, self.date_file_path)
                print(f"Backtest period: {past_date_str} → {current_date_str} ({days} trading days)")

                # 起点快照
                initial_account = self._read_account_file(self.account_file_path)
                self._log_account_snapshot(past_date_str, initial_account)

                # ── 逐日回放 ──
                next_date_str = past_date_str
                for i in range(days):
                    print(f"Processing day {i+1}/{days}...")
                    self.exchange.pre_tick()
                    sleep(0.4)
                    self.hook.on_tick()
                    sleep(0.4)
                    self.exchange.post_tick()
                    sleep(0.4)

                    current_account = self._read_account_file(self.account_file_path)
                    self._log_account_snapshot(next_date_str, current_account)

                    # 推进一个交易日
                    next_date_str = self._find_past_trading_day(next_date_str, trading_days, -1)
                    print(f"  Current trading day: {next_date_str}")
                    temp_date_data['current_date'] = next_date_str
                    self._write_date_file(temp_date_data, self.date_file_path)
                    print(f"  Day {i+1} completed")

                # 计算指标
                metrics = self._calculate_metrics()
                output_lines = [
                    f"✅ Backtest completed: {past_date_str} → {current_date_str} ({days} trading days)",
                    "",
                    "📊 Performance Metrics (based on Net Assets):",
                ]
                for name, value in metrics.items():
                    output_lines.append(f"  {name}: {value}")

                # 写日志
                backtest_result["period"] = {"start_date": past_date_str, "end_date": current_date_str}
                backtest_result["metrics"] = metrics
                backtest_result["snapshots"] = self.backtest_snapshots
                self._log_results(backtest_result)

                return "\n".join(output_lines)

            except Exception as e:
                import traceback
                error_msg = f"❌ Error during backtest execution: {str(e)}\n{traceback.format_exc()}"
                backtest_result["status"] = "failed"
                backtest_result["error"] = str(e)
                self._log_results(backtest_result)
                return error_msg
            finally:
                # 关键：无论成败都还原状态，避免污染真实账户
                self._restore_original_state()
                self.backtest_snapshots = []

        return backtest

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    "Run a backtest from N trading days ago to today using the strategy "
                    "defined in `workspace/strategy.py`. Returns performance metrics including "
                    "Total Return, Annualized Return, Sharpe Ratio, Max Drawdown, Calmar Ratio "
                    "and Average Position Rates. Returns zero values when no orders are executed "
                    "during the backtest period."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of trading days to go back for backtest (must be positive integer)",
                            "maximum": 120,
                        }
                    },
                    "required": ["days"],
                },
            }
        raise ValueError(f"Unsupported producer: {producer}")
