"""
策略内下单工具（add_order）

功能概述：
    在 strategy.py 内部调用，绕过 LLM 直接写入新订单到 account.json。
    与 agent.toolkit.AddOrderTool 的差别：
      - 此函数是程序接口，异常会向上抛出
      - 工具版本会捕获异常并以字符串形式返回

设计要点：
    - 同样校验 BUY/SELL / 正价 / 正数量 / 100 的整数倍
    - 订单时间戳固定为当日 14:30（A 股收盘前撮合）
    - 订单 ID 由 uuid 前 8 位生成
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ..schemas import OrderSchema, OrderType, OrderStatus


def add_order(
    symbol: str,
    order_type: str,
    price: float,
    quantity: int,
    account_file_path: str = "../persistent/account.json",
    date_file_path: str = "../persistent/date.json",
) -> None:
    """提交一个新订单到账户 JSON。

    参数:
        symbol:           股票代码。
        order_type:       "BUY" 或 "SELL"。
        price:            下单价格（> 0）。
        quantity:         数量（> 0，且为 100 的整数倍）。
        account_file_path:账户 JSON 路径。
        date_file_path:   date.json 路径。

    异常:
        ValueError: 输入校验失败 / current_date 缺失。
        FileNotFoundError: 账户或日期文件不存在。
    """
    # ── 输入校验 ──
    if order_type.upper() not in ["BUY", "SELL"]:
        raise ValueError(f"order_type must be 'BUY' or 'SELL', got '{order_type}'")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    if quantity <= 0:
        raise ValueError(f"quantity must be positive, got {quantity}")
    if not os.path.exists(account_file_path):
        raise FileNotFoundError(f"Account file not found: {account_file_path}")
    if not os.path.exists(date_file_path):
        raise FileNotFoundError(f"Date file not found: {date_file_path}")

    try:
        with open(date_file_path, 'r', encoding='utf-8') as f:
            date_data = json.load(f)

        current_date_str = date_data.get('current_date')
        if not current_date_str:
            raise ValueError("current_date not found in date file")

        # 订单时间戳：14:30 收盘前撮合
        current_date = datetime.fromisoformat(current_date_str)
        order_timestamp = current_date.replace(hour=14, minute=30, second=0, microsecond=0)

        with open(account_file_path, 'r', encoding='utf-8') as f:
            account_data = json.load(f)

        # 生成订单 ID 并实例化
        order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
        new_order = OrderSchema(
            order_id=order_id,
            symbol=symbol.upper(),
            order_type=OrderType[order_type.upper()],
            price=price,
            quantity=quantity,
            timestamp=order_timestamp,
            status=OrderStatus.PENDING,
        )

        # 序列化：datetime -> str，枚举 -> value
        order_dict = new_order.model_dump()
        order_dict['timestamp'] = order_dict['timestamp'].isoformat()
        order_dict['order_type'] = order_dict['order_type'].value
        order_dict['status'] = order_dict['status'].value

        if "orders" not in account_data:
            account_data["orders"] = []
        account_data["orders"].append(order_dict)

        Path(account_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(account_file_path, 'w', encoding='utf-8') as f:
            json.dump(account_data, f, indent=2, ensure_ascii=False, default=str)

    except FileNotFoundError:
        raise
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Failed to parse JSON file: {str(e)}", e.doc, e.pos)
    except Exception as e:
        raise Exception(f"Error adding order: {str(e)}") from e
