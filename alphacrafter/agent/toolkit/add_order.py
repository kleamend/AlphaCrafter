"""
下单工具（AddOrderTool）

功能概述：
    让 LLM Agent 在交易仿真中提交一个新的订单（买/卖）。
    订单状态被初始化为 PENDING，由后续的 Exchange/撮合流程按规则处理。

数据流：
    ┌────────────┐  读取   ┌──────────────────┐  写入   ┌──────────────────┐
    │ date.json  │ ─────→ │ AddOrderTool     │ ─────→ │ account.json     │
    │ (当前日期) │         │ (生成新订单)     │         │ (orders 列表)    │
    └────────────┘         └──────────────────┘         └──────────────────┘

关键约束：
    - A 股最小一手 = 100 股，下单数量必须为 100 的整数倍。
    - 订单时间戳固定为当前交易日的 14:30（模拟收盘前撮合）。
    - 订单 ID 由 uuid 前 8 位生成，保证唯一性。
"""

from typing import Dict, Any, Callable, List, Optional
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from .base import BaseTool
from alphacrafter.sim.schemas import OrderSchema, OrderType, OrderStatus


class AddOrderTool(BaseTool):
    """新增订单工具。"""

    def __init__(self, account_file_path: str = "../persistent/account.json", date_file_path: str = "../persistent/date.json"):
        """初始化下单工具。

        参数:
            account_file_path: 账户 JSON 文件路径，包含可用现金、持仓与历史订单。
            date_file_path:    当前日期 JSON 文件路径（用于生成订单时间戳）。
        """
        self.account_file_path = account_file_path
        self.date_file_path = date_file_path

    def get_name(self) -> str:
        """工具注册名。"""
        return "add_order"

    # ── 持久化辅助方法 ────────────────────────────────────

    def _read_account_file(self) -> Dict[str, any]:
        """读取并解析 account.json。"""
        if not os.path.exists(self.account_file_path):
            raise FileNotFoundError(f"Account file not found: {self.account_file_path}")
        with open(self.account_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _read_date_file(self) -> Dict[str, any]:
        """读取并解析 date.json。"""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_account_file(self, data: Dict[str, any]) -> None:
        """将账户数据写回 account.json，自动创建缺失目录。"""
        Path(self.account_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.account_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    # ── 序列化辅助方法 ────────────────────────────────────

    def _order_to_dict(self, order: OrderSchema) -> Dict:
        """将 OrderSchema 转 JSON 友好的字典。

        处理三处类型转换：
          - datetime -> ISO 字符串
          - 枚举字段 -> 字符串值
        """
        order_dict = order.model_dump()
        order_dict['timestamp'] = order_dict['timestamp'].isoformat()
        order_dict['order_type'] = order_dict['order_type'].value
        order_dict['status'] = order_dict['status'].value
        return order_dict

    def _order_to_string(self, order: OrderSchema) -> str:
        """将订单序列化为 `field: value` 多行字符串，便于 LLM 阅读。"""
        lines = [f"Order {order.order_id} added:"]
        lines.append(f"symbol: {order.symbol}")
        lines.append(f"order_type: {order.order_type.value}")
        lines.append(f"price: {order.price:.2f}")
        lines.append(f"quantity: {order.quantity}")
        lines.append(f"timestamp: {order.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"status: {order.status.value}")
        return "\n".join(lines)

    # ── 工具实现工厂 ────────────────────────────────────

    def get_implementation(self) -> Callable:
        def add_order(
            symbol: str,
            order_type: str,
            price: float,
            quantity: int,
        ) -> str:
            """提交一个新订单。

            参数:
                symbol:     股票代码（例如 "SZ002245"）。
                order_type: "BUY" 或 "SELL"。
                price:      下单价格（> 0）。
                quantity:   数量（> 0，且为 100 的整数倍）。

            返回值:
                成功时为订单的 `field: value` 多行文本；失败时为错误描述。
            """
            try:
                # ── 输入校验 ──
                if order_type.upper() not in ["BUY", "SELL"]:
                    return f"Error: order_type must be 'BUY' or 'SELL', got '{order_type}'"
                if price <= 0:
                    return f"Error: price must be positive, got {price}"
                if quantity <= 0:
                    return f"Error: quantity must be positive, got {quantity}"
                # A 股"一手"为 100 股，下单数量必须是其整数倍
                if quantity % 100 != 0:
                    return f"Error: quantity must be a multiple of 100 (board lot), got {quantity}"

                # ── 读取上下文 ──
                account_data = self._read_account_file()
                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                if not current_date_str:
                    return "Error: current_date not found in date file"

                # ── 构造订单时间戳：固定为 14:30 收盘前撮合 ──
                current_date = datetime.fromisoformat(current_date_str)
                order_timestamp = current_date.replace(hour=14, minute=30, second=0, microsecond=0)

                # ── 生成订单 ID 并实例化 OrderSchema ──
                order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
                new_order = OrderSchema(
                    order_id=order_id,
                    symbol=symbol,
                    order_type=OrderType[order_type.upper()],
                    price=price,
                    quantity=quantity,
                    timestamp=order_timestamp,
                    status=OrderStatus.PENDING,
                )

                # 追加到账户订单列表
                if "orders" not in account_data:
                    account_data["orders"] = []
                account_data["orders"].append(self._order_to_dict(new_order))

                # 持久化
                self._write_account_file(account_data)

                return self._order_to_string(new_order)

            except FileNotFoundError as e:
                return f"Error: {str(e)}"
            except Exception as e:
                return f"Error adding order: {str(e)}"

        return add_order

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer in ("OpenAI", "MiniMax"):
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    "Add a new order to the account. Creates an order with PENDING status "
                    "using current date from date.json with time 14:30. "
                    "Quantity must be a multiple of 100 (board lot). Requires account file to exist."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock code",
                        },
                        "order_type": {
                            "type": "string",
                            "enum": ["BUY", "SELL"],
                            "description": "Order type - BUY or SELL",
                        },
                        "price": {
                            "type": "number",
                            "description": "Order price per share",
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "Number of shares to trade (must be multiple of 100)",
                        },
                    },
                    "required": ["symbol", "order_type", "price", "quantity"],
                },
            }
        raise ValueError(f"Unsupported producer: {producer}")
