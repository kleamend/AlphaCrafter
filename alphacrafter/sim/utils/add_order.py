import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ..schemas import OrderSchema, OrderType, OrderStatus

def add_order(
    symbol: str,
    order_type: str,
    price: float,
    quantity: int,
    account_file_path: str = "../persistent/account.json",
    date_file_path: str = "../persistent/date.json"
) -> None:
    """
    Add a new order to the account.
    
    Args:
        symbol: Stock code
        order_type: Order type ("BUY" or "SELL")
        price: Order price per share
        quantity: Number of shares to trade (must be multiple of 100)
        account_file_path: Path to the account JSON file
        date_file_path: Path to the date JSON file containing current_date
    """
    # Validate inputs
    if order_type.upper() not in ["BUY", "SELL"]:
        raise ValueError(f"order_type must be 'BUY' or 'SELL', got '{order_type}'")
    
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    
    if quantity <= 0:
        raise ValueError(f"quantity must be positive, got {quantity}")
    
    # Check if account file exists
    if not os.path.exists(account_file_path):
        raise FileNotFoundError(f"Account file not found: {account_file_path}")
    
    # Read date file to get current date
    if not os.path.exists(date_file_path):
        raise FileNotFoundError(f"Date file not found: {date_file_path}")

    try:
        with open(date_file_path, 'r', encoding='utf-8') as f:
            date_data = json.load(f)
        
        current_date_str = date_data.get('current_date')
        if not current_date_str:
            raise ValueError("current_date not found in date file")
        
        # Convert current date to datetime and set time to 14:30
        current_date = datetime.fromisoformat(current_date_str)
        order_timestamp = current_date.replace(hour=14, minute=30, second=0, microsecond=0)

        # Read account data
        with open(account_file_path, 'r', encoding='utf-8') as f:
            account_data = json.load(f)
        
        # Generate order ID
        order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
        
        # Create order using OrderSchema
        new_order = OrderSchema(
            order_id=order_id,
            symbol=symbol.upper(),
            order_type=OrderType[order_type.upper()],
            price=price,
            quantity=quantity,
            timestamp=order_timestamp,
            status=OrderStatus.PENDING
        )
        
        # Convert to dict for JSON serialization
        order_dict = new_order.model_dump()
        order_dict['timestamp'] = order_dict['timestamp'].isoformat()
        order_dict['order_type'] = order_dict['order_type'].value
        order_dict['status'] = order_dict['status'].value
        
        # Initialize orders list if not exists
        if "orders" not in account_data:
            account_data["orders"] = []
        
        # Add order
        account_data["orders"].append(order_dict)
        
        # Ensure directory exists
        Path(account_file_path).parent.mkdir(parents=True, exist_ok=True)

        # Save back to file
        with open(account_file_path, 'w', encoding='utf-8') as f:
            json.dump(account_data, f, indent=2, ensure_ascii=False, default=str)

    except FileNotFoundError:
        # Re-raise FileNotFoundError as is
        raise
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Failed to parse JSON file: {str(e)}", e.doc, e.pos)
    except Exception as e:
        raise Exception(f"Error adding order: {str(e)}") from e