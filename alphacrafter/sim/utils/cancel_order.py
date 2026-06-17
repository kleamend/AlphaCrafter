"""
策略内撤单工具（cancel_order）

功能概述：
    在 strategy.py 内部调用，删除指定 order_id 的 PENDING 订单。
    与 agent.toolkit.CancelOrderTool 行为一致（仅删除 PENDING）。
"""

import json
import os
import sys
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ..schemas import OrderSchema, OrderType, OrderStatus


def cancel_order(
    order_id: str,
    account_file_path: str = "../persistent/account.json",
) -> None:
    """按订单 ID 撤销 PENDING 订单（物理删除）。

    参数:
        order_id:         目标订单 ID。
        account_file_path:账户 JSON 路径。

    异常:
        FileNotFoundError: 账户文件不存在。
        ValueError: 订单不存在 / 状态不允许撤单。
    """
    if not os.path.exists(account_file_path):
        raise FileNotFoundError(f"Account file not found: {account_file_path}")

    try:
        with open(account_file_path, 'r', encoding='utf-8') as f:
            account_data = json.load(f)

        if "orders" not in account_data or not account_data["orders"]:
            raise ValueError("No orders found in account")

        # 遍历查找
        order_found = False
        updated_orders = []
        for order in account_data["orders"]:
            if order.get("order_id") == order_id:
                order_found = True
                # 业务规则：仅 PENDING 可撤
                if order.get("status") != "PENDING":
                    raise ValueError(
                        f"Cannot cancel order {order_id}: status is {order.get('status')} "
                        f"(only PENDING orders can be cancelled)"
                    )
                # 不加入 updated_orders，等价于删除
                continue
            else:
                updated_orders.append(order)

        if not order_found:
            raise ValueError(f"Order not found: {order_id}")

        account_data["orders"] = updated_orders

        Path(account_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(account_file_path, 'w', encoding='utf-8') as f:
            json.dump(account_data, f, indent=2, ensure_ascii=False, default=str)

    except FileNotFoundError:
        raise
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Failed to parse account file: {str(e)}", e.doc, e.pos)
    except ValueError:
        raise
    except Exception as e:
        raise Exception(f"Error cancelling order: {str(e)}") from e
