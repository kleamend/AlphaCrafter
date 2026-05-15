import pandas as pd
import json
import os
from datetime import datetime
from typing import Optional

def get_stock_daily_data(
    symbol: str,
    days: int,
    dataset_dir_path: str = "../persistent/stock_data",
    date_file_path: str = "../persistent/date.json"
) -> pd.DataFrame:
    """
    Get historical stock data for a symbol.
    
    Args:
        symbol: Stock code (e.g., "SZ.002245")
        days: Number of past trading days to retrieve (including current_date)
        dataset_dir_path: Path to the folder containing stock CSV files
        date_file_path: Path to the date.json file containing current_date
        
    Returns:
        DataFrame with historical stock data containing columns: date, open, close, high, low, volume, amount, 
        amplitude, pct_change, change, turnover, market_cap, pe_ttm, pb, ps_ttm, dividend_yield_rate
        The DataFrame is sorted from recent to old dates (descending order), with the most recent trading day first.
        
    Raises:
        ValueError: If days <= 0
        FileNotFoundError: If date file or stock data file not found
        KeyError: If current_date not found in date file or required columns missing
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
        
        # Check stock data file exists
        csv_path = os.path.join(dataset_dir_path, f"{symbol}.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Stock data file not found: {csv_path}")
        
        # Load CSV
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            raise Exception(f"Failed to read CSV file: {str(e)}") from e
        
        # Check if date column exists
        if 'date' not in df.columns:
            raise KeyError(f"'date' column not found in {csv_path}")
        
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
        stock_data = historical_data.tail(days)
        
        # Sort from recent to old (descending order)
        # This ensures the most recent trading day appears last
        stock_data = stock_data.sort_values('date', ascending=True)
        
        # Reset index to clean up the DataFrame
        stock_data = stock_data.reset_index(drop=True)
        
        return stock_data
        
    except FileNotFoundError:
        # Re-raise FileNotFoundError as is
        raise
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Failed to parse date file: {str(e)}", e.doc, e.pos)
    except (ValueError, KeyError):
        # Re-raise ValueError and KeyError as is
        raise
    except Exception as e:
        raise Exception(f"Error getting stock data: {str(e)}") from e