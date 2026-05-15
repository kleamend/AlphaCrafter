from typing import Dict, Any
import json
from pathlib import Path

def get_date_str(date_file_path: str = "../persistent/date.json") -> str:
    """
    Load date file and return current date string.
    
    Args:
        date_file_path: Path to the date JSON file
        
    Returns:
        String containing the current date in YYYY-MM-DD format
    """
    date_path = Path(date_file_path)
    
    if not date_path.exists():
        raise FileNotFoundError(f"Date file not found: {date_file_path}")
    
    with open(date_path, 'r') as f:
        date_dict = json.load(f)
    
    return date_dict["current_date"]