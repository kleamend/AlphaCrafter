from typing import Dict, Any
import json
from pathlib import Path

def get_account_dict(account_file_path: str = "../persistent/account.json") -> Dict[str, Any]:
    """
    Load account from JSON file and return as dictionary
    
    Args:
        account_file_path: Path to the account JSON file
        
    Returns:
        Dictionary containing the raw account data
    """
    account_path = Path(account_file_path)
    
    if not account_path.exists():
        raise FileNotFoundError(f"Account file not found: {account_file_path}")
    
    with open(account_path, 'r') as f:
        account_dict = json.load(f)
    
    return account_dict