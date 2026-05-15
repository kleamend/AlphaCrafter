import pandas as pd
import json
import os
from datetime import datetime
from typing import Optional

def get_index_daily_data(
    symbol: str,
    days: int,
    dataset_dir_path: str = "../persistent/index_data",
    date_file_path: str = "../persistent/date.json"
) -> pd.DataFrame:
    """
    Get historical index data for an index code.
    
    Args:
        symbol: Index code (e.g., "SH.000001")
        days: Number of past trading days to retrieve (including current_date)
        dataset_dir_path: Path to the folder containing index CSV files
        date_file_path: Path to the date.json file containing current_date
        
    Returns:
        DataFrame with historical index data containing columns: date, open, close, high, low, volume, amount
        The DataFrame is sorted from recent to old dates (descending order), with the most recent trading day first.
        
    Raises:
        ValueError: If days <= 0
        FileNotFoundError: If date file or index data file not found
        KeyError: If current_date not found in date file or date column missing
        json.JSONDecodeError: If JSON parsing fails
        Exception: For other errors during data retrieval
    """
    # Validate input
    if days <= 0:
        raise ValueError(f"days must be positive, got {days}")
    
    # Check date file exists
    if not os.path.exists(date_file_path):
        raise FileNotFoundError(f"Date file not found: {date_file_path}")
    
    try:
        # Read date file to get current date
        with open(date_file_path, 'r', encoding='utf-8') as f:
            date_data = json.load(f)
        
        current_date_str = date_data.get('current_date')
        if not current_date_str:
            raise KeyError("current_date not found in date file")
        
        # Convert current date to datetime
        current_date = pd.to_datetime(current_date_str)
        
        # Check index data file exists
        csv_path = os.path.join(dataset_dir_path, f"{symbol}.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Index data file not found: {csv_path}")
        
        # Load CSV
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            raise Exception(f"Failed to read CSV file: {str(e)}") from e
        
        # Check if required columns exist
        required_columns = ['date', 'open', 'close', 'high', 'low']
        for col in required_columns:
            if col not in df.columns:
                raise KeyError(f"'{col}' column not found in {csv_path}")
        
        # Convert date to datetime (handles '2020-01-02' string format)
        df['date'] = pd.to_datetime(df['date'])
        
        # Sort by date to ensure proper order before filtering
        df = df.sort_values('date')
        
        # Filter data up to current_date
        mask = df['date'] <= current_date
        historical_data = df[mask]
        
        if historical_data.empty:
            return None  # No data available before or on current_date
        
        # Get the last N days of data (most recent N days)
        index_data = historical_data.tail(days)
        
        # Sort from recent to old (descending order)
        # This ensures the most recent trading day appears last
        index_data = index_data.sort_values('date', ascending=True)
        
        # Reset index to clean up the DataFrame
        index_data = index_data.reset_index(drop=True)
        
        return index_data
        
    except FileNotFoundError:
        # Re-raise FileNotFoundError as is
        raise
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Failed to parse date file: {str(e)}", e.doc, e.pos)
    except (ValueError, KeyError):
        # Re-raise ValueError and KeyError as is
        raise
    except Exception as e:
        raise Exception(f"Error getting index data: {str(e)}") from e