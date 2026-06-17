"""
账户 / 持仓 Pydantic 数据模型

定义仿真中账户相关强类型结构：
  - PositionDirection: 持仓方向（LONG / SHORT）
  - PositionData:      单一持仓记录
  - AccountSchema:     账户整体快照（资金、持仓、订单、关注列表）

注意：
  A 股仿真默认不创建 SHORT 持仓（仅 LONG），但 schema 层保留了方向字段
  以兼容美股版 Exchange。
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from .order import OrderSchema
from enum import Enum


class PositionDirection(str, Enum):
    """持仓方向枚举。"""
    LONG  = "LONG"   # 多头
    SHORT = "SHORT"  # 空头（仅美股仿真使用）


class PositionData(BaseModel):
    """单只股票的持仓信息。"""
    symbol:            str              = Field(..., description="Stock code")
    direction:         PositionDirection = Field(
        default=PositionDirection.LONG,
        description="Position direction (long/short)",
    )
    quantity:          int              = Field(..., description="Total position quantity")
    available_quantity: int             = Field(..., description="Quantity available for sale (T+1 rules apply)")
    cost_price:        float            = Field(..., description="Average cost price")
    current_price:     float            = Field(..., description="Latest market price")
    market_value:      float            = Field(..., description="quantity * current_price")
    profit_loss:       float            = Field(..., description="Floating profit/loss")
    profit_loss_rate:  float            = Field(..., description="Floating profit/loss rate")


class AccountSchema(BaseModel):
    """账户整体快照，所有可被 Agent 控制的字段都在这里。"""

    total_assets:            float             = Field(..., description="Total assets (= net assets in this sim)")
    net_assets:              float             = Field(..., description="Net assets = cash + market value")
    available_cash:          float             = Field(..., description="Free cash for new orders")
    market_value:            float             = Field(..., description="Sum of position market values")
    total_profit_loss:       float             = Field(..., description="Total P&L vs initial capital")
    total_profit_loss_rate:  float             = Field(..., description="Total P&L rate")
    gross_position_rate:     float             = Field(..., description="|long| + |short| / net_assets")
    net_position_rate:       float             = Field(..., description="(long - short) / net_assets")
    positions:               List[PositionData] = Field(default_factory=list, description="Position list")
    orders:                  List[OrderSchema]  = Field(default_factory=list, description="All orders (any status)")
    watch_list:              List[str]          = Field(default_factory=list, description="Symbol watch list")
