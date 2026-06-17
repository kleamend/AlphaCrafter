"""
读取当前仿真日期（get_date_str）

功能概述：
    从 date.json 中读取 current_date 字段并以字符串形式返回，
    供 Agent 在构造上下文时把"今天"的信息透出。
"""

from typing import Dict, Any
import json
from pathlib import Path


def get_date_str(date_file_path: str = "../persistent/date.json") -> str:
    """读取仿真当前日期。

    参数:
        date_file_path: date.json 路径。

    返回值:
        YYYY-MM-DD 格式的当前日期字符串。

    异常:
        FileNotFoundError: 文件不存在。
    """
    date_path = Path(date_file_path)

    if not date_path.exists():
        raise FileNotFoundError(f"Date file not found: {date_file_path}")

    with open(date_path, 'r') as f:
        date_dict = json.load(f)

    return date_dict["current_date"]
