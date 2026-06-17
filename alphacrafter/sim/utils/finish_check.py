"""
仿真结束条件检查（finish_check）

功能概述：
    判断当前日期是否已经达到回测窗口的最后一个交易日；
    若达到，Agent 应停止继续 step，进入收尾。

设计要点：
    - 任何异常都不抛出，全部降级为返回 False，避免阻塞仿真流程
    - 实际项目里可通过环境变量 / 配置文件切换策略，但当前仅判断日期
"""

import json
import os
from typing import Dict, Any


def finish_check() -> bool:
    """判断当前日期是否已是最后一个交易日。

    返回值:
        True 表示仿真应当结束；False 表示还可以继续推进。
    """
    date_file_path = "../persistent/date.json"

    try:
        if not os.path.exists(date_file_path):
            print(f"Warning: Date file not found: {date_file_path}")
            return False

        with open(date_file_path, 'r', encoding='utf-8') as f:
            date_data = json.load(f)

        current_date = date_data.get('current_date')
        trading_days = date_data.get('trading_days', [])

        if not current_date:
            print("Warning: current_date not found in date file")
            return False
        if not trading_days:
            print("Warning: trading_days not found in date file")
            return False

        last_trading_day = trading_days[-1]
        is_last = (current_date == last_trading_day)

        if is_last:
            print(f"✅ Finish condition met: current_date {current_date} is the last trading day")
        else:
            print(f"⏳ Current date {current_date} is not the last trading day ({last_trading_day})")

        return is_last

    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse date file: {e}")
        return False
    except Exception as e:
        print(f"Warning: Error in finish_check: {e}")
        return False
