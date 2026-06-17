"""
回测快照评估工具（evaluate.py）

功能概述：
    读取 StepTool / BacktestTool 写出的 snapshot.json 账户快照序列，
    计算并打印一份"组合业绩报告"，便于研究/对比。

关键指标:
    - 总收益 / 年化收益（ARR）
    - 年化波动率 / 年化超额波动率
    - 超额收益 / 信息比率（Excess Sharpe）
    - 最大回撤及其持续天数
    - 胜率 / 盈亏比
    - 正负交易日数

用法:
    python -m utils.evaluate
    （默认从 sandbox/grid-live-a/logs/snapshot.json 读取）
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
import os

# ── 全局配置 ───────────────────────────

INITIAL_CAPITAL = 10_000_000                # 初始资金
TRADING_DAYS_PER_YEAR = 243                 # 年交易日数（A 股口径）
BENCHMARK_ANNUAL_RETURN = 0.0125            # 基准年化收益
BENCHMARK_DAILY_RETURN = (1 + BENCHMARK_ANNUAL_RETURN) ** (1 / TRADING_DAYS_PER_YEAR) - 1


def load_log_file(file_path):
    """从 JSON 加载 snapshot 日志（保持原结构）。"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def calculate_performance_metrics(account_snapshots, initial_capital):
    """基于账户快照计算完整业绩指标。

    参数:
        account_snapshots:  StepTool 写出的 list[dict]，每条含 current_date + account
        initial_capital:    初始资金

    返回值:
        {
          'metrics': dict,
          'daily_returns', 'excess_daily_returns', 'cumulative_returns',
          'dates', 'total_assets_list',
        }
    """
    dates = []
    total_assets_list = []

    # 抽取日期与总资产
    for snapshot in account_snapshots:
        date_str = snapshot.get('current_date', '')
        if not date_str and 'timestamp' in snapshot:
            date_str = snapshot['timestamp'].split()[0]
        account = snapshot.get('account', {})
        total_assets = account.get('total_assets', 0)
        dates.append(date_str)
        total_assets_list.append(total_assets)

    # 构造时间序列与日收益
    returns_series = pd.Series(total_assets_list, index=pd.to_datetime(dates))
    daily_returns = returns_series.pct_change().dropna()

    # 总收益
    total_return = (returns_series.iloc[-1] - initial_capital) / initial_capital
    total_days = len(returns_series)

    # 年化收益（ARR）
    if total_days > 0:
        annualized_return = (total_return + 1) ** (TRADING_DAYS_PER_YEAR / total_days) - 1
    else:
        annualized_return = 0

    # ── 超额收益 ──
    excess_return = annualized_return - BENCHMARK_ANNUAL_RETURN
    excess_return_percent = excess_return * 100

    excess_daily_returns = daily_returns - BENCHMARK_DAILY_RETURN

    if len(excess_daily_returns) > 0:
        annualized_excess_volatility = excess_daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        annualized_excess_volatility = 0

    if annualized_excess_volatility > 0:
        excess_sharpe = excess_return / annualized_excess_volatility
    else:
        excess_sharpe = 0

    # 年化波动率
    if len(daily_returns) > 0:
        annualized_volatility = daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        annualized_volatility = 0

    # 普通 Sharpe（参考用）
    if annualized_volatility > 0:
        sharpe_ratio = (annualized_return - BENCHMARK_ANNUAL_RETURN) / annualized_volatility
    else:
        sharpe_ratio = 0

    # ── 回撤分析 ──
    cumulative_returns = returns_series / returns_series.iloc[0]
    rolling_max = cumulative_returns.expanding().max()
    drawdown = (cumulative_returns - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    # 最大回撤持续天数：扫描回撤序列，记录从回撤开始到恢复的最长片段
    max_drawdown_duration = 0
    current_duration = 0
    in_drawdown = False
    for dd in drawdown:
        if dd < 0 and not in_drawdown:
            in_drawdown = True
            current_duration = 1
        elif dd < 0 and in_drawdown:
            current_duration += 1
        elif dd == 0 and in_drawdown:
            in_drawdown = False
            max_drawdown_duration = max(max_drawdown_duration, current_duration)
            current_duration = 0

    # ── 胜率 / 盈亏比 ──
    positive_days = (daily_returns > 0).sum()
    negative_days = (daily_returns < 0).sum()
    win_rate = positive_days / len(daily_returns) if len(daily_returns) > 0 else 0
    avg_win = daily_returns[daily_returns > 0].mean() if positive_days > 0 else 0
    avg_loss = abs(daily_returns[daily_returns < 0].mean()) if negative_days > 0 else 0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    return {
        'metrics': {
            'initial_capital': initial_capital,
            'final_assets': returns_series.iloc[-1],
            'total_return': total_return,
            'total_return_percent': total_return * 100,
            'annualized_return': annualized_return,
            'annualized_return_percent': annualized_return * 100,
            # 超额收益
            'excess_return': excess_return,
            'excess_return_percent': excess_return_percent,
            'excess_sharpe': excess_sharpe,
            'annualized_excess_volatility': annualized_excess_volatility,
            'annualized_excess_volatility_percent': annualized_excess_volatility * 100,
            # 参考指标
            'benchmark_annual_return': BENCHMARK_ANNUAL_RETURN,
            'benchmark_annual_return_percent': BENCHMARK_ANNUAL_RETURN * 100,
            'annualized_volatility': annualized_volatility,
            'annualized_volatility_percent': annualized_volatility * 100,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_percent': max_drawdown * 100,
            'max_drawdown_duration_days': max_drawdown_duration,
            'win_rate': win_rate,
            'win_rate_percent': win_rate * 100,
            'profit_loss_ratio': profit_loss_ratio,
            'total_days': total_days,
            'trading_days': len(daily_returns),
            'positive_days': positive_days,
            'negative_days': negative_days,
        },
        'daily_returns': daily_returns,
        'excess_daily_returns': excess_daily_returns,
        'cumulative_returns': cumulative_returns,
        'dates': dates,
        'total_assets_list': total_assets_list,
    }


def print_metrics(metrics):
    """把业绩字典以"分块报告"的形式打印到控制台。"""
    print("\n" + "=" * 60)
    print("Portfolio Performance Report")
    print("=" * 60)

    print(f"\nInitial Capital: ¥{metrics['initial_capital']:,.2f}")
    print(f"Final Assets: ¥{metrics['final_assets']:,.2f}")
    print(f"Total Return: {metrics['total_return_percent']:.2f}%")
    print(f"Total P&L: ¥{metrics['final_assets'] - metrics['initial_capital']:,.2f}")

    print("\n" + "-" * 40)
    print("Absolute Performance (ARR)")
    print("-" * 40)
    print(f"Annualized Return (ARR): {metrics['annualized_return_percent']:.2f}%")
    print(f"Annualized Volatility: {metrics['annualized_volatility_percent']:.2f}%")
    print(f"Benchmark Return: {metrics['benchmark_annual_return_percent']:.2f}%")

    print("\n" + "-" * 40)
    print("Excess Performance (vs Benchmark)")
    print("-" * 40)
    print(f"Excess Annualized Return: {metrics['excess_return_percent']:.2f}%")
    print(f"Excess Sharpe Ratio (Information Ratio): {metrics['excess_sharpe']:.4f}")
    print(f"Excess Volatility (Tracking Error): {metrics['annualized_excess_volatility_percent']:.2f}%")

    print("\n" + "-" * 40)
    print("Drawdown Analysis")
    print("-" * 40)
    print(f"Max Drawdown: {metrics['max_drawdown_percent']:.2f}%")
    print(f"Max Drawdown Duration: {metrics['max_drawdown_duration_days']} days")

    print("\n" + "-" * 40)
    print("Trading Statistics")
    print("-" * 40)
    print(f"Total Days: {metrics['total_days']} days")
    print(f"Trading Days: {metrics['trading_days']} days")
    print(f"Positive Days: {metrics['positive_days']} days")
    print(f"Negative Days: {metrics['negative_days']} days")
    print(f"Win Rate: {metrics['win_rate_percent']:.2f}%")
    print(f"Profit/Loss Ratio: {metrics['profit_loss_ratio']:.4f}")

    print("\n" + "=" * 60)


def main():
    """主入口：默认从固定路径读 snapshot 并打印报告。"""
    input_file = 'sandbox/grid-live-a/logs/snapshot.json'

    if not os.path.exists(input_file):
        print(f"Error: file not found {input_file}")
        return

    print(f"Loading file: {input_file}")
    data = load_log_file(input_file)
    print("Calculating performance metrics...")
    result = calculate_performance_metrics(data, INITIAL_CAPITAL)
    print_metrics(result['metrics'])

    # 构造结果 DataFrame 供外部复用（不自动落盘）
    df = pd.DataFrame({
        'date': result['cumulative_returns'].index,
        'total_assets': result['total_assets_list'],
        'cumulative_return': result['cumulative_returns'].values,
        'daily_return': result['daily_returns'].reindex(result['cumulative_returns'].index, fill_value=0),
        'excess_daily_return': result['excess_daily_returns'].reindex(result['cumulative_returns'].index, fill_value=0),
    })


if __name__ == "__main__":
    main()
