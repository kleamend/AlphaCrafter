"""
读取账户原始字典（get_account_dict）

功能概述：
    供 Agent 在每轮上下文构建中读取"当前账户快照"原文（不解析为 Pydantic）。
    与 get_account_dict() 配套使用的 get_date_str() 在另一个文件中定义。
"""

from typing import Dict, Any
import json
from pathlib import Path


def get_account_dict(account_file_path: str = "../persistent/account.json") -> Dict[str, Any]:
    """加载账户 JSON 并以字典形式返回。

    参数:
        account_file_path: 账户 JSON 文件路径。

    返回值:
        原始 JSON 数据（dict）。

    异常:
        FileNotFoundError: 文件不存在。
    """
    account_path = Path(account_file_path)

    if not account_path.exists():
        raise FileNotFoundError(f"Account file not found: {account_file_path}")

    with open(account_path, 'r') as f:
        account_dict = json.load(f)

    return account_dict
