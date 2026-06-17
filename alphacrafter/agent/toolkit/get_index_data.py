"""
指数历史数据查询工具（GetIndexDataTool）

功能概述：
    与 GetStockDataTool 类似，但针对市场指数（CSI300、S&P 500 等），
    字段裁剪为 8 个核心列（不含估值四件套，因为指数本身不存在 PE 等单股指标）。

数据流：
    ┌─────────────────────┐  读取   ┌──────────────────┐  重采样  ┌────────────┐
    │ ../persistent/      │ ─────→ │ _load_index_data │ ───────→ │ _format    │
    │ index_data/XXX.csv  │         │ (缓存层)         │          │ _data_row  │
    └─────────────────────┘         └──────────────────┘          └────────────┘
"""

from typing import Dict, Any, Callable
import json
import os
import pandas as pd
from pathlib import Path

from .base import BaseTool


class GetIndexDataTool(BaseTool):
    """获取指数历史数据的工具。"""

    def __init__(self, dataset_dir_path: str = "../persistent/index_data", date_file_path: str = "../persistent/date.json"):
        """初始化指数查询工具。

        参数:
            dataset_dir_path: 指数 CSV 文件所在目录。
            date_file_path:   当前日期 JSON 文件路径。
        """
        self.dataset_dir_path = dataset_dir_path
        self.date_file_path = date_file_path

        # 指数没有 PE/PB 等个股估值指标，仅保留 8 列
        self.metric_columns = [
            'date', 'open', 'close', 'high', 'low', 'volume', 'change', 'pct_change',
        ]

        # 内存缓存
        self.market_data: Dict[str, pd.DataFrame] = {}

    def get_name(self) -> str:
        """工具注册名。"""
        return "get_index_data"

    # ── 辅助方法 ────────────────────────────────────

    def _read_date_file(self) -> Dict[str, any]:
        """读取 date.json。"""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_index_data(self, symbol: str) -> pd.DataFrame:
        """从 CSV 加载并预处理指数数据。

        与股票版本结构相同，但只读取 8 列核心字段。
        """
        if symbol in self.market_data:
            return self.market_data[symbol]

        csv_path = os.path.join(self.dataset_dir_path, f"{symbol}.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Index data file not found: {csv_path}")

        required_cols = ['date', 'open', 'close', 'high', 'low', 'volume', 'change', 'pct_change']
        try:
            df = pd.read_csv(csv_path, usecols=required_cols)
        except ValueError:
            df = pd.read_csv(csv_path)
            df = df[required_cols]

        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df.sort_index()

        self.market_data[symbol] = df
        return df

    def _resample_data(self, df: pd.DataFrame, period: str, current_date: pd.Timestamp) -> pd.DataFrame:
        """重采样并过滤（与股票版一致，但聚合字段更少）。"""
        if period == 'daily':
            df_reset = df.reset_index()
            return df_reset[df_reset['date'] <= current_date]

        if period == 'weekly':
            rule = 'W-FRI'
        elif period == 'monthly':
            rule = 'ME'
        else:
            raise ValueError(f"Unsupported period: {period}")

        agg_dict = {
            'open': 'first',
            'close': 'last',
            'high': 'max',
            'low': 'min',
            'volume': 'sum',
            'change': 'last',
            'pct_change': 'last',
        }
        resampled = df.resample(rule).agg(agg_dict)
        resampled = resampled.dropna()
        resampled.reset_index(inplace=True)
        resampled = resampled[resampled['date'] <= current_date]
        return resampled

    def _format_data_row(self, date: pd.Timestamp, row: pd.Series, period: str = "daily") -> str:
        """单行数据 -> 文本（无估值字段）。"""
        date_str = date.strftime('%Y-%m-%d')
        metrics = []

        if period != 'daily':
            metrics.append(f"[{period.capitalize()}]")

        if 'open'  in row and pd.notna(row['open']):  metrics.append(f"Open={row['open']:.4f}")
        if 'high'  in row and pd.notna(row['high']):  metrics.append(f"High={row['high']:.4f}")
        if 'low'   in row and pd.notna(row['low']):   metrics.append(f"Low={row['low']:.4f}")
        if 'close' in row and pd.notna(row['close']): metrics.append(f"Close={row['close']:.4f}")

        if 'volume'     in row and pd.notna(row['volume']):     metrics.append(f"Volume={row['volume']:.0f}")
        if 'pct_change' in row and pd.notna(row['pct_change']): metrics.append(f"PctChange={row['pct_change']:.4f}%")
        if 'change'     in row and pd.notna(row['change']):     metrics.append(f"Change={row['change']:+.4f}")

        return f"{date_str}: {', '.join(metrics)}"

    # ── 工具实现工厂 ────────────────────────────────────

    def get_implementation(self) -> Callable:
        def get_index_data(symbol: str, length: int, period: str = "daily") -> str:
            """查询一支指数最近 N 个周期的历史数据。

            参数:
                symbol: 指数代码（如 '000001.SH' 上证综指、'SPX' 标普 500）。
                length: 返回最近多少个周期。
                period: 'daily' / 'weekly' / 'monthly'。

            返回值:
                格式化后的多行文本。
            """
            try:
                if length <= 0:
                    return f"Error: length must be positive, got {length}"
                if period not in ['daily', 'weekly', 'monthly']:
                    return f"Error: period must be 'daily', 'weekly', or 'monthly', got {period}"

                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                if not current_date_str:
                    return "Error: current_date not found in date file"
                current_date = pd.to_datetime(current_date_str)

                df = self._load_index_data(symbol.upper())
                mask = df.index <= current_date
                historical_data = df[mask].copy()
                if historical_data.empty:
                    return f"No data found for index {symbol} before or on {current_date_str}"

                resampled_data = self._resample_data(historical_data, period, current_date)
                if resampled_data.empty:
                    return f"No {period} data available for index {symbol}"

                resampled_data = resampled_data.sort_values('date', ascending=False)
                period_data = resampled_data.head(length)

                period_names = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months'}
                period_name = period_names.get(period, 'periods')
                lines = [
                    f"Index Data for {symbol} (last {len(period_data)} {period_name} up to {current_date_str}):"
                ]
                for _, row in period_data.iterrows():
                    lines.append(self._format_data_row(row['date'], row, period))

                # 摘要：起止价差、平均成交量
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
                return f"Error getting index data: {str(e)}"

        return get_index_data

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    "Get historical index data including date, open, close, high, low, volume, "
                    "change, and pct_change. Supports daily, weekly, and monthly sampling periods."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Index code (e.g., '000001.SH' for Shanghai Composite, 'SPX' for S&P 500)",
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
