import json
import os
from typing import Dict, Any

def finish_check() -> bool:
    """
    Check if the simulation should finish based on current_date reaching the last trading day.
        
    Returns:
        True if current_date is the last trading day, False otherwise
    """
    date_file_path = "../persistent/date.json"
    
    try:
        # Read date file
        if not os.path.exists(date_file_path):
            print(f"Warning: Date file not found: {date_file_path}")
            return False
        
        with open(date_file_path, 'r', encoding='utf-8') as f:
            date_data = json.load(f)
        
        # Get current_date and trading_days
        current_date = date_data.get('current_date')
        trading_days = date_data.get('trading_days', [])
        
        if not current_date:
            print("Warning: current_date not found in date file")
            return False
        
        if not trading_days:
            print("Warning: trading_days not found in date file")
            return False
        
        # Check if current_date is the last trading day
        last_trading_day = trading_days[-1]
        is_last = (current_date == last_trading_day)
        
        if is_last:
            print(f"✅ Finish condition met: current_date {current_date} is the last trading day")
        else:
            print(f"⏳ Current date {current_date} is not the last trading day ({last_trading_day})")
        
        return is_last
        
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse date file: {e}")
        return False
    except Exception as e:
        print(f"Warning: Error in finish_check: {e}")
        return False