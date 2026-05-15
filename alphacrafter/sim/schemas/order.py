from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

class OrderStatus(str, Enum):
    """Order status enumeration"""
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class OrderType(str, Enum):
    """Order type enumeration"""
    BUY = "BUY"
    SELL = "SELL"
    
class OrderSchema(BaseModel):
    """Order base schema"""
    order_id: str = Field(..., description="Unique order identifier")
    symbol: str = Field(..., description="Stock code")
    order_type: OrderType = Field(..., description="Order type: buy/sell")
    price: float = Field(..., description="Order price")
    quantity: int = Field(..., description="Order quantity")
    timestamp: datetime = Field(default_factory=datetime.now, description="Order creation time")
    status: OrderStatus = Field(OrderStatus.PENDING, description="Order status")

class OrderResultSchema(BaseModel):
    """Order result data model - returned when order succeeds or fails"""
    order_id: str = Field(..., description="Unique order identifier")
    symbol: str = Field(..., description="Stock code")
    order_type: OrderType = Field(..., description="Order type")
    status: OrderStatus = Field(..., description="Final order status")
    timestamp: datetime = Field(default_factory=datetime.now, description="Result timestamp")
    executed_quantity: Optional[int] = Field(None, description="Actual executed quantity")
    executed_price: Optional[float] = Field(None, description="Actual average execution price")
    executed_amount: Optional[float] = Field(None, description="Actual execution amount")
    commission: Optional[float] = Field(None, description="Transaction fee")
    message: Optional[str] = Field(None, description="Additional information or error message")