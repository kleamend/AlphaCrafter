"""
股票历史数据查询工具（GetStockDataTool）

功能概述：
    从本地 CSV 文件中读取指定股票的历史行情，并支持日 / 周 / 月三种采样频率。
    数据会经过日期过滤、重采样、统计聚合，最后格式化为多行文本供 LLM 阅读。

数据流：
    ┌───────────────────┐  读取   ┌──────────────────┐  过滤/重采样  ┌────────────┐
    │ ../persistent/    │ ─────→ │ _load_stock_data │ ────────────→ │ _format    │
    │ stock_data/XXX.csv│         │ (缓存层)         │              │ _data_row  │
    └───────────────────┘         └──────────────────┘              └────────────┘
                                      ↑                                │
                                      │ 命中缓存直接返回                ▼
                                  dict[DataFrame]                   LLM 文本

设计要点：
    - 内存缓存：同一股票不重复读 CSV，提高 Agent 多轮调用效率。
    - 重采样规则：
        * 日线：直接过滤到 current_date 之前
        * 周线：以周五为周结束（W-FRI），用各聚合函数
        * 月线：ME 规则（月末），取月度汇总
    - 估值字段：除 OHLCV 外还包含 PE / PS / PB / DYR（股息率），
      这些字段对因子研究和选股尤其重要。
"""

from typing import Dict, Any, Callable
import json
import os
import pandas as pd
from pathlib import Path

from .base import BaseTool


class GetStockDataTool(BaseTool):
    """获取股票历史数据（支持日/周/月频率）的工具。"""

    def __init__(self, dataset_dir_path: str = "../persistent/stock_data", date_file_path: str = "../persistent/date.json"):
        """初始化查询工具。

        参数:
            dataset_dir_path: 股票 CSV 文件所在目录。
            date_file_path:   当前日期 JSON 文件路径。
        """
        self.dataset_dir_path = dataset_dir_path
        self.date_file_path = date_file_path

        # 字段顺序：先行情，再价差，再估值（与原始 CSV 顺序保持一致）
        self.metric_columns = [
            'date', 'open', 'close', 'high', 'low', 'volume', 'change', 'pct_change',
            'PE', 'PS', 'PB', 'DYR',
        ]

        # 内存缓存：symbol -> 已加载的 DataFrame
        self.market_data: Dict[str, pd.DataFrame] = {}

    def get_name(self) -> str:
        """工具注册名。"""
        return "get_stock_data"

    # ── 辅助方法 ────────────────────────────────────

    def _read_date_file(self) -> Dict[str, any]:
        """读取 date.json。"""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_stock_data(self, symbol: str) -> pd.DataFrame:
        """从 CSV 加载并预处理股票数据。

        处理步骤:
          1. 命中缓存直接返回
          2. 优先只读必需列（节省内存），失败时回退读全表
          3. date 转 datetime 并设为索引
          4. 按日期升序排序

        返回值:
            以日期为索引的 DataFrame。
        """
        if symbol in self.market_data:
            return self.market_data[symbol]

        csv_path = os.path.join(self.dataset_dir_path, f"{symbol}.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Stock data file not found: {csv_path}")

        required_cols = [
            'date', 'open', 'close', 'high', 'low', 'volume',
            'change', 'pct_change', 'PE', 'PS', 'PB', 'DYR',
        ]
        try:
            df = pd.read_csv(csv_path, usecols=required_cols)
        except ValueError:
            # 文件结构不符合预期：全量读取再截取
            df = pd.read_csv(csv_path)
            available_cols = [col for col in required_cols if col in df.columns]
            df = df[available_cols]

        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df.sort_index()

        # 写入缓存
        self.market_data[symbol] = df
        return df

    def _resample_data(self, df: pd.DataFrame, period: str, current_date: pd.Timestamp) -> pd.DataFrame:
        """将日线数据重采样为周/月线并过滤到 current_date 之前。

        参数:
            df:           日线 DataFrame（日期为索引）。
            period:       'daily' / 'weekly' / 'monthly'。
            current_date: 当前日期，只保留 <= 该日期的样本。

        返回值:
            已重采样的 DataFrame（date 为普通列）。
        """
        if period == 'daily':
            df_reset = df.reset_index()
            return df_reset[df_reset['date'] <= current_date]

        # 重采样规则
        if period == 'weekly':
            rule = 'W-FRI'   # 周线以周五收尾
        elif period == 'monthly':
            rule = 'ME'      # 月末
        else:
            raise ValueError(f"Unsupported period: {period}")

        # 各列的聚合函数：开/收/高/低/量都有各自的语义
        agg_dict = {
            'open': 'first',     # 当期首个交易日的开盘
            'close': 'last',     # 当期最后一个交易日的收盘
            'high': 'max',       # 当期最高
            'low': 'min',        # 当期最低
            'volume': 'sum',     # 当期累计成交量
            'change': 'last',    # 当期最后一日的绝对涨跌
            'pct_change': 'last',  # 当期最后一日的涨跌幅
            'PE': 'last',
            'PS': 'last',
            'PB': 'last',
            'DYR': 'last',
        }
        resampled = df.resample(rule).agg(agg_dict)
        resampled = resampled.dropna()           # 丢弃无交易的周期
        resampled.reset_index(inplace=True)      # 把日期从 index 变回列
        resampled = resampled[resampled['date'] <= current_date]
        return resampled

    def _format_data_row(self, date: pd.Timestamp, row: pd.Series, period: str = "daily") -> str:
        """将一行数据格式化为 "日期: 字段=值, ..." 形式的可读字符串。"""
        date_str = date.strftime('%Y-%m-%d')
        metrics = []

        # 非日线时在行首标注周期类型
        if period != 'daily':
            metrics.append(f"[{period.capitalize()}]")

        # OHLC 行情
        if 'open'  in row and pd.notna(row['open']):  metrics.append(f"Open={row['open']:.4f}")
        if 'high'  in row and pd.notna(row['high']):  metrics.append(f"High={row['high']:.4f}")
        if 'low'   in row and pd.notna(row['low']):   metrics.append(f"Low={row['low']:.4f}")
        if 'close' in row and pd.notna(row['close']): metrics.append(f"Close={row['close']:.4f}")

        # 量价变动
        if 'volume'     in row and pd.notna(row['volume']):     metrics.append(f"Volume={row['volume']:.0f}")
        if 'pct_change' in row and pd.notna(row['pct_change']): metrics.append(f"PctChange={row['pct_change']:.4f}%")
        if 'change'     in row and pd.notna(row['change']):     metrics.append(f"Change={row['change']:+.4f}")

        # 估值四件套
        if 'PE'  in row and pd.notna(row['PE']):  metrics.append(f"PE={row['PE']:.2f}")
        if 'PS'  in row and pd.notna(row['PS']):  metrics.append(f"PS={row['PS']:.2f}")
        if 'PB'  in row and pd.notna(row['PB']):  metrics.append(f"PB={row['PB']:.2f}")
        if 'DYR' in row and pd.notna(row['DYR']): metrics.append(f"DYR={row['DYR']:.4f}")

        return f"{date_str}: {', '.join(metrics)}"

    # ── 工具实现工厂 ────────────────────────────────────

    def get_implementation(self) -> Callable:
        def get_stock_data(symbol: str, length: int, period: str = "daily") -> str:
            """查询一支股票最近 N 个周期的历史数据。

            参数:
                symbol: 股票代码（如 'AAPL'）。
                length: 返回最近多少个周期（包含当日）。
                period: 'daily' / 'weekly' / 'monthly'。

            返回值:
                格式化后的多行文本（含数据列表与可选的统计汇总）。
            """
            try:
                if length <= 0:
                    return f"Error: length must be positive, got {length}"
                if period not in ['daily', 'weekly', 'monthly']:
                    return f"Error: period must be 'daily', 'weekly', or 'monthly', got {period}"

                # 读取当前日期（仿真时钟）
                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                if not current_date_str:
                    return "Error: current_date not found in date file"
                current_date = pd.to_datetime(current_date_str)

                # 加载并按 current_date 过滤
                df = self._load_stock_data(symbol.upper())
                mask = df.index <= current_date
                historical_data = df[mask].copy()
                if historical_data.empty:
                    return f"No data found for symbol {symbol} before or on {current_date_str}"

                # 重采样
                resampled_data = self._resample_data(historical_data, period, current_date)
                if resampled_data.empty:
                    return f"No {period} data available for symbol {symbol}"

                # 取最近 N 个周期（降序后取 head）
                resampled_data = resampled_data.sort_values('date', ascending=False)
                period_data = resampled_data.head(length)

                # 构造输出
                period_names = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months'}
                period_name = period_names.get(period, 'periods')
                lines = [
                    f"Stock Data for {symbol} (last {len(period_data)} {period_name} up to {current_date_str}):"
                ]
                for _, row in period_data.iterrows():
                    lines.append(self._format_data_row(row['date'], row, period))

                # 统计摘要：起止价差、累计涨跌幅、平均成交量
                if len(period_data) > 1:
                    most_recent_close = period_data.iloc[0]['close']
                    oldest_close = period_data.iloc[-1]['close']
                    price_change = most_recent_close - oldest_close
                    pct_change = (price_change / oldest_close) * 100 if oldest_close != 0 else 0

                    most_recent_date = period_data.iloc[0]['date']
                    oldest_date = period_data.iloc[-1]['date']
                    lines.append(
                        f"Period: {oldest_date.strftime('%Y-%m-%d')} → {most_recent_date.strftime('%Y-%m-%d')}"
                    )
                    lines.append(f"Change: {price_change:+.4f} ({pct_change:+.4f}%)")
                    if 'volume' in period_data.columns:
                        avg_volume = period_data['volume'].mean()
                        lines.append(f"Avg Volume: {avg_volume:.0f}")

                return "\n".join(lines)

            except FileNotFoundError as e:
                return f"Error: {str(e)}"
            except Exception as e:
                return f"Error getting stock data: {str(e)}"

        return get_stock_data

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer in ("OpenAI", "MiniMax"):
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    "Get historical stock data for a symbol including date, open, close, high, low, "
                    "volume, change, pct_change, PE, PS, PB, and DYR (dividend yield). "
                    "Supports daily, weekly, and monthly sampling periods."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock code",
                        },
                        "length": {
                            "type": "integer",
                            "description": (
                                "Number of past periods to retrieve (including current date). "
                                "For daily: number of trading days, for weekly: number of weeks, "
                                "for monthly: number of months."
                            ),
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "period": {
                            "type": "string",
                            "description": "Sampling period - 'daily', 'weekly', or 'monthly'",
                            "enum": ["daily", "weekly", "monthly"],
                            "default": "daily",
                        },
                    },
                    "required": ["symbol", "length"],
                },
            }
        raise ValueError(f"Unsupported producer: {producer}")
