from typing import Dict, Any, Callable, List, Optional
import json
import os
import sys
import uuid
from datetime import datetime, time
from pathlib import Path

from .base import BaseTool
from alphacrafter.sim.schemas import OrderSchema, OrderType, OrderStatus


class AddOrderTool(BaseTool):
    """Tool for adding new orders to the account."""
    
    def __init__(self, account_file_path: str = "../persistent/account.json", date_file_path: str = "../persistent/date.json"):
        """
        Initialize the add order tool.
        
        Args:
            account_file_path: Path to the account JSON file
            date_file_path: Path to the date JSON file
        """
        self.account_file_path = account_file_path
        self.date_file_path = date_file_path
    
    def get_name(self) -> str:
        return "add_order"
    
    def _read_account_file(self) -> Dict[str, any]:
        """Read and parse the account file."""
        if not os.path.exists(self.account_file_path):
            raise FileNotFoundError(f"Account file not found: {self.account_file_path}")
        
        with open(self.account_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _read_date_file(self) -> Dict[str, any]:
        """Read and parse the date.json file."""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _write_account_file(self, data: Dict[str, any]) -> None:
        """Write data back to account file."""
        # Ensure directory exists
        Path(self.account_file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.account_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    def _order_to_dict(self, order: OrderSchema) -> Dict:
        """Convert OrderSchema to dictionary for JSON serialization."""
        order_dict = order.model_dump()
        # Convert datetime to string
        order_dict['timestamp'] = order_dict['timestamp'].isoformat()
        # Convert enums to strings
        order_dict['order_type'] = order_dict['order_type'].value
        order_dict['status'] = order_dict['status'].value
        return order_dict
    
    def _order_to_string(self, order: OrderSchema) -> str:
        """Convert OrderSchema to string with field:value format."""
        lines = [f"Order {order.order_id} added:"]
        lines.append(f"symbol: {order.symbol}")
        lines.append(f"order_type: {order.order_type.value}")
        lines.append(f"price: {order.price:.2f}")
        lines.append(f"quantity: {order.quantity}")
        lines.append(f"timestamp: {order.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"status: {order.status.value}")
        return "\n".join(lines)
    
    def get_implementation(self) -> Callable:
        def add_order(
            symbol: str,
            order_type: str,
            price: float,
            quantity: int
        ) -> str:
            """
            Add a new order to the account.
            
            Args:
                symbol: Stock code (e.g., "SZ002245")
                order_type: Order type ("BUY" or "SELL")
                price: Order price
                quantity: Number of shares (must be multiple of 100)
                
            Returns:
                String with order addition result (order details in field:value format)
            """
            try:
                # Validate inputs
                if order_type.upper() not in ["BUY", "SELL"]:
                    return f"Error: order_type must be 'BUY' or 'SELL', got '{order_type}'"
                
                if price <= 0:
                    return f"Error: price must be positive, got {price}"
                
                if quantity <= 0:
                    return f"Error: quantity must be positive, got {quantity}"
                
                # Validate quantity is multiple of 100 (board lot requirement)
                if quantity % 100 != 0:
                    return f"Error: quantity must be a multiple of 100 (board lot), got {quantity}"
                
                # Read current account
                account_data = self._read_account_file()
                
                # Read date file to get current date
                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                
                if not current_date_str:
                    return "Error: current_date not found in date file"
                
                # Convert current date to datetime and set time to 14:30
                current_date = datetime.fromisoformat(current_date_str)
                order_timestamp = current_date.replace(hour=14, minute=30, second=0, microsecond=0)
                
                # Generate order ID
                order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
                
                # Create order using OrderSchema
                new_order = OrderSchema(
                    order_id=order_id,
                    symbol=symbol,
                    order_type=OrderType[order_type.upper()],
                    price=price,
                    quantity=quantity,
                    timestamp=order_timestamp,
                    status=OrderStatus.PENDING
                )
                
                # Initialize orders list if not exists
                if "orders" not in account_data:
                    account_data["orders"] = []
                
                # Convert to dict and add
                account_data["orders"].append(self._order_to_dict(new_order))
                
                # Save back to file
                self._write_account_file(account_data)
                
                # Return formatted order details
                return self._order_to_string(new_order)
                
            except FileNotFoundError as e:
                return f"Error: {str(e)}"
            except Exception as e:
                return f"Error adding order: {str(e)}"
        
        return add_order
    
    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """Return tool description based on the producer."""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Add a new order to the account. Creates an order with PENDING status using current date from date.json with time 14:30. Quantity must be a multiple of 100 (board lot). Requires account file to exist.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock code"
                        },
                        "order_type": {
                            "type": "string",
                            "enum": ["BUY", "SELL"],
                            "description": "Order type - BUY or SELL"
                        },
                        "price": {
                            "type": "number",
                            "description": "Order price per share",
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "Number of shares to trade (must be multiple of 100)",
                        }
                    },
                    "required": ["symbol", "order_type", "price", "quantity"]
                }
            }
        else:
            raise ValueError(f"Unsupported producer: {producer}")