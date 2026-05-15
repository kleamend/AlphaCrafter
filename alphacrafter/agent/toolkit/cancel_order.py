from typing import Dict, Any, Callable, List, Optional
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from .base import BaseTool

class CancelOrderTool(BaseTool):
    """Tool for canceling existing orders by deletion."""
    
    def __init__(self, account_file_path: str = "../persistent/account.json"):
        """
        Initialize the cancel order tool.
        
        Args:
            account_file_path: Path to the account JSON file
        """
        self.account_file_path = account_file_path
    
    def get_name(self) -> str:
        return "cancel_order"
    
    def _read_account_file(self) -> Dict[str, any]:
        """Read and parse the account file."""
        if not os.path.exists(self.account_file_path):
            return {"orders": []}
        
        with open(self.account_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _write_account_file(self, data: Dict[str, any]) -> None:
        """Write data back to account file."""
        Path(self.account_file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.account_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    def get_implementation(self) -> Callable:
        def cancel_order(order_id: str) -> str:
            """
            Cancel a pending order by removing it from the account.
            
            Args:
                order_id: ID of the order to cancel (remove)
                
            Returns:
                String with cancellation result
            """
            try:
                # Read current account
                account_data = self._read_account_file()
                
                if "orders" not in account_data or not account_data["orders"]:
                    return f"No orders found in account"
                
                # Find and remove the order
                initial_count = len(account_data["orders"])
                order_found = False
                
                # Filter out the order with matching ID and PENDING status
                updated_orders = []
                for order in account_data["orders"]:
                    if order.get("order_id") == order_id:
                        order_found = True
                        # Only remove if it's PENDING
                        if order.get("status") != "PENDING":
                            return f"Cannot cancel order {order_id}: status is {order.get('status')} (only PENDING orders can be cancelled)"
                        # Skip this order (don't add to updated_orders) -> effectively deleting it
                        continue
                    else:
                        updated_orders.append(order)
                
                if not order_found:
                    return f"Order not found: {order_id}"
                
                # Update orders list
                account_data["orders"] = updated_orders
                
                # Save back to file
                self._write_account_file(account_data)
                
                return f"Order {order_id} cancelled"
                
            except Exception as e:
                return f"Error cancelling order: {str(e)}"
        
        return cancel_order
    
    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """Return tool description based on the producer."""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Cancel a pending order by removing it from the account. Only orders with PENDING status can be cancelled.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "ID of the order to cancel (remove)"
                        }
                    },
                    "required": ["order_id"]
                }
            }
        else:
            raise ValueError(f"Unsupported producer: {producer}")