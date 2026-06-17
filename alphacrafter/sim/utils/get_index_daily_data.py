"""
读取指数历史数据（get_index_daily_data）

功能概述：
    在 strategy.py 中调用，读取指数行情并返回 pandas DataFrame。
    行为与 agent.toolkit.GetIndexDataTool 类似，但面向"策略代码"调用方
    （非 LLM 工具调用），返回结构化数据而非格式化文本。
"""

import pandas as pd
import json
import os
from typing import Optional


def get_index_daily_data(
    symbol: str,
    days: int,
    dataset_dir_path: str = "../persistent/index_data",
    date_file_path: str = "../persistent/date.json",
) -> Optional[pd.DataFrame]:
    """读取指定指数的最近 N 个交易日数据。

    参数:
        symbol:          指数代码（如 'SH.000001'）。
        days:            需要的天数（> 0）。
        dataset_dir_path:指数 CSV 目录。
        date_file_path:  date.json 路径。

    返回值:
        DataFrame（按日期升序），列至少包含 date / open / close / high / low；
        无可用数据时返回 None。

    异常:
        ValueError: days <= 0。
        FileNotFoundError: date.json 或指数 CSV 不存在。
        KeyError: 必要列缺失。
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
            raise FileNotFoundError(f"Index data file not found: {csv_path}")

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            raise Exception(f"Failed to read CSV file: {str(e)}") from e

        # 校验必要列
        required_columns = ['date', 'open', 'close', 'high', 'low']
        for col in required_columns:
            if col not in df.columns:
                raise KeyError(f"'{col}' column not found in {csv_path}")

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        # 仅保留 <= current_date 的历史
        historical_data = df[df['date'] <= current_date]
        if historical_data.empty:
            return None

        # 取最近 N 个交易日
        index_data = historical_data.tail(days)
        # 注意文档说"desc"但实际 sort 升序；保留实现行为不变
        index_data = index_data.sort_values('date', ascending=True)
        index_data = index_data.reset_index(drop=True)

        return index_data

    except FileNotFoundError:
        raise
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Failed to parse date file: {str(e)}", e.doc, e.pos)
    except (ValueError, KeyError):
        raise
    except Exception as e:
        raise Exception(f"Error getting index data: {str(e)}") from e
