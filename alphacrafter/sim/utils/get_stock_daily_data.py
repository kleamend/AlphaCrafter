"""
读取股票历史数据（get_stock_daily_data）

功能概述：
    在 strategy.py 中调用，读取单只股票行情并返回 pandas DataFrame。
    与 agent.toolkit.GetStockDataTool 的差别：
      - 此函数返回 DataFrame（程序内部使用）
      - 工具版返回格式化字符串（供 LLM 阅读）
"""

import pandas as pd
import json
import os
from typing import Optional


def get_stock_daily_data(
    symbol: str,
    days: int,
    dataset_dir_path: str = "../persistent/stock_data",
    date_file_path: str = "../persistent/date.json",
) -> Optional[pd.DataFrame]:
    """读取指定股票的最近 N 个交易日数据。

    参数:
        symbol:          股票代码（如 'SZ.002245'）。
        days:            需要的天数（> 0）。
        dataset_dir_path:股票 CSV 目录。
        date_file_path:  date.json 路径。

    返回值:
        DataFrame（按日期升序），至少包含 date / open / close / high / low 等列；
        无可用数据时返回 None。

    异常:
        ValueError: days <= 0。
        FileNotFoundError: date.json 或股票 CSV 不存在。
        KeyError: 缺少必要列。
        json.JSONDecodeError: date.json 解析失败。
    """
    if days <= 0:
        raise ValueError(f"days must be positive, got {days}")

    if not os.path.exists(date_file_path):
        raise FileNotFoundError(f"Date file not found: {date_file_path}")

    try:
        with open(date_file_path, 'r', encoding='utf-8') as f:
            date_data = json.load(f)

        current_date_str = date_data.get('current_date')
        if not current_date_str:
            raise KeyError("current_date not found in date file")

        current_date = pd.to_datetime(current_date_str)

        csv_path = os.path.join(dataset_dir_path, f"{symbol}.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Stock data file not found: {csv_path}")

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            raise Exception(f"Failed to read CSV file: {str(e)}") from e

        if 'date' not in df.columns:
            raise KeyError(f"'date' column not found in {csv_path}")

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        historical_data = df[df['date'] <= current_date]
        if historical_data.empty:
            return None

        stock_data = historical_data.tail(days)
        stock_data = stock_data.sort_values('date', ascending=True)
        stock_data = stock_data.reset_index(drop=True)

        return stock_data

    except FileNotFoundError:
        raise
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Failed to parse date file: {str(e)}", e.doc, e.pos)
    except (ValueError, KeyError):
        raise
    except Exception as e:
        raise Exception(f"Error getting stock data: {str(e)}") from e
