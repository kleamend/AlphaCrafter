"""
撤单工具（CancelOrderTool）

功能概述：
    在仿真中按订单 ID 撤销一笔挂单（status == PENDING）。
    已成交或已拒绝的订单不可撤销，工具会显式返回错误。

设计要点：
    - 通过物理删除（filter + 重写）实现撤单，简单可靠；
      仅 PENDING 状态的订单才会被删除。
    - 若目标订单不存在 / 状态不允许，返回清晰错误信息，便于 LLM 重试或调整。
"""

from typing import Dict, Any, Callable
import json
import os
from pathlib import Path

from .base import BaseTool


class CancelOrderTool(BaseTool):
    """按订单 ID 撤销挂单的工具。"""

    def __init__(self, account_file_path: str = "../persistent/account.json"):
        """初始化撤单工具。

        参数:
            account_file_path: 账户 JSON 文件路径。
        """
        self.account_file_path = account_file_path

    def get_name(self) -> str:
        """工具注册名。"""
        return "cancel_order"

    # ── 持久化辅助方法 ────────────────────────────────────

    def _read_account_file(self) -> Dict[str, any]:
        """读取账户 JSON；不存在时返回空账户（仅含空 orders）。"""
        if not os.path.exists(self.account_file_path):
            return {"orders": []}
        with open(self.account_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_account_file(self, data: Dict[str, any]) -> None:
        """将更新后的账户数据写回磁盘。"""
        Path(self.account_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.account_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    # ── 工具实现工厂 ────────────────────────────────────

    def get_implementation(self) -> Callable:
        def cancel_order(order_id: str) -> str:
            """按 ID 撤销挂单。

            参数:
                order_id: 要撤销的订单 ID。

            返回值:
                成功/失败描述字符串。
            """
            try:
                account_data = self._read_account_file()
                if "orders" not in account_data or not account_data["orders"]:
                    return f"No orders found in account"

                # ── 遍历查找目标订单 ──
                order_found = False
                updated_orders = []
                for order in account_data["orders"]:
                    if order.get("order_id") == order_id:
                        order_found = True
                        # 业务规则：仅 PENDING 订单可撤
                        if order.get("status") != "PENDING":
                            return (
                                f"Cannot cancel order {order_id}: "
                                f"status is {order.get('status')} (only PENDING orders can be cancelled)"
                            )
                        # 不加入 updated_orders，等价于从列表中删除
                        continue
                    else:
                        updated_orders.append(order)

                if not order_found:
                    return f"Order not found: {order_id}"

                # 写回
                account_data["orders"] = updated_orders
                self._write_account_file(account_data)

                return f"Order {order_id} cancelled"

            except Exception as e:
                return f"Error cancelling order: {str(e)}"

        return cancel_order

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer in ("OpenAI", "MiniMax"):
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    "Cancel a pending order by removing it from the account. "
                    "Only orders with PENDING status can be cancelled."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "ID of the order to cancel (remove)",
                        }
                    },
                    "required": ["order_id"],
                },
            }
        raise ValueError(f"Unsupported producer: {producer}")
