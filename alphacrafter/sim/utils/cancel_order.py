import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ..schemas import OrderSchema, OrderType, OrderStatus

def cancel_order(
    order_id: str,
    account_file_path: str = "../persistent/account.json"
) -> None:
    """
    Cancel a pending order by removing it from the account.
    
    Args:
        order_id: ID of the order to cancel (remove)
        account_file_path: Path to the account JSON file
    """
    # Check if account file exists
    if not os.path.exists(account_file_path):
        raise FileNotFoundError(f"Account file not found: {account_file_path}")
    
    try:
        # Read account data
        with open(account_file_path, 'r', encoding='utf-8') as f:
            account_data = json.load(f)
        
        if "orders" not in account_data or not account_data["orders"]:
            raise ValueError("No orders found in account")
        
        # Find and remove the order
        order_found = False
        updated_orders = []
        
        for order in account_data["orders"]:
            if order.get("order_id") == order_id:
                order_found = True
                # Only remove if it's PENDING
                if order.get("status") != "PENDING":
                    raise ValueError(f"Cannot cancel order {order_id}: status is {order.get('status')} (only PENDING orders can be cancelled)")
                # Skip this order (don't add to updated_orders)
                continue
            else:
                updated_orders.append(order)
        
        if not order_found:
            raise ValueError(f"Order not found: {order_id}")
        
        # Update orders list
        account_data["orders"] = updated_orders
        
        # Ensure directory exists
        Path(account_file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Save back to file
        with open(account_file_path, 'w', encoding='utf-8') as f:
            json.dump(account_data, f, indent=2, ensure_ascii=False, default=str)
        
        # Success - no return value needed
        
    except FileNotFoundError:
        # Re-raise FileNotFoundError as is
        raise
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Failed to parse account file: {str(e)}", e.doc, e.pos)
    except ValueError:
        # Re-raise ValueError as is
        raise
    except Exception as e:
        raise Exception(f"Error cancelling order: {str(e)}") from e