"""
订单相关 Pydantic 数据模型

定义仿真中订单与订单执行结果的强类型结构：
  - OrderStatus:   订单状态枚举（PENDING / SUCCESS / FAILED / EXPIRED）
  - OrderType:     订单方向枚举（BUY / SELL）
  - OrderSchema:   订单主体（含 ID、symbol、价格、数量、时间戳、状态）
  - OrderResultSchema: 撮合/失败时的结果回报

被引用方:
    - sim.utils.add_order / cancel_order
    - sim.exchange_a / exchange_us  的 _process_orders
    - agent.toolkit.AddOrderTool / CancelOrderTool
"""

from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class OrderStatus(str, Enum):
    """订单状态枚举。"""
    PENDING  = "PENDING"   # 挂单中，等待撮合或撤单
    SUCCESS  = "SUCCESS"   # 已成交
    FAILED   = "FAILED"    # 失败（资金不足 / 持仓不足 / 价格异常）
    EXPIRED  = "EXPIRED"   # 过期（A 股 / 美股均为 PENDING 超过 7 个交易日）


class OrderType(str, Enum):
    """订单方向枚举。"""
    BUY  = "BUY"
    SELL = "SELL"


class OrderSchema(BaseModel):
    """订单主体 schema。"""
    order_id:   str       = Field(..., description="Unique order identifier")
    symbol:     str       = Field(..., description="Stock code")
    order_type: OrderType = Field(..., description="Order type: buy/sell")
    price:      float     = Field(..., description="Order price")
    quantity:   int       = Field(..., description="Order quantity")
    timestamp:  datetime  = Field(
        default_factory=datetime.now,
        description="Order creation time (set to 14:30 for A-share, 15:30 ET for US)",
    )
    status:     OrderStatus = Field(
        OrderStatus.PENDING,
        description="Order status",
    )


class OrderResultSchema(BaseModel):
    """订单执行结果 schema。撮合/失败时由 Exchange 产出。"""
    order_id:          str                 = Field(..., description="Unique order identifier")
    symbol:            str                 = Field(..., description="Stock code")
    order_type:        OrderType           = Field(..., description="Order type")
    status:            OrderStatus         = Field(..., description="Final order status")
    timestamp:         datetime            = Field(
        default_factory=datetime.now,
        description="Result timestamp",
    )
    executed_quantity: Optional[int]       = Field(None, description="Actual executed quantity")
    executed_price:    Optional[float]     = Field(None, description="Actual average execution price")
    executed_amount:   Optional[float]     = Field(None, description="Actual execution amount")
    commission:        Optional[float]     = Field(None, description="Transaction fee")
    message:           Optional[str]       = Field(None, description="Additional info or error message")
