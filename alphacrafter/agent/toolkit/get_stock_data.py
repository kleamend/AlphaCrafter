from typing import Dict, Any, Callable, List, Optional
import json
import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from .base import BaseTool


class GetStockDataTool(BaseTool):
    """Tool for getting historical stock data for a symbol with support for daily, weekly, monthly sampling."""
    
    def __init__(self, dataset_dir_path: str = "../persistent/stock_data", date_file_path: str = "../persistent/date.json"):
        """
        Initialize the get stock data tool.
        
        Args:
            dataset_dir_path: Path to the folder containing stock CSV files
            date_file_path: Path to the date.json file containing current_date
        """
        self.dataset_dir_path = dataset_dir_path
        self.date_file_path = date_file_path
        
        # Define column order for metrics (reduced to 8 core columns)
        self.metric_columns = [
            'date', 'open', 'close', 'high', 'low', 'volume', 'change', 'pct_change'
        ]
        
        # Cache for loaded data
        self.market_data: Dict[str, pd.DataFrame] = {}
    
    def get_name(self) -> str:
        return "get_stock_data"
    
    def _read_date_file(self) -> Dict[str, any]:
        """Read and parse the date.json file."""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_stock_data(self, symbol: str) -> pd.DataFrame:
        """Load stock data from CSV file."""
        # Check cache first
        if symbol in self.market_data:
            return self.market_data[symbol]
        
        # Construct file path
        csv_path = os.path.join(self.dataset_dir_path, f"{symbol}.csv")
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Stock data file not found: {csv_path}")
        
        # Load CSV - only read required columns to save memory
        required_cols = ['date', 'open', 'close', 'high', 'low', 'volume', 'change', 'pct_change']
        try:
            df = pd.read_csv(csv_path, usecols=required_cols)
        except ValueError:
            # Fallback: read all columns then select
            df = pd.read_csv(csv_path)
            df = df[required_cols]
        
        # Convert date to datetime for proper sorting and comparison
        df['date'] = pd.to_datetime(df['date'])
        
        # Set date as index for resampling
        df.set_index('date', inplace=True)
        
        # Sort by date
        df = df.sort_index()
        
        # Cache the data
        self.market_data[symbol] = df
        
        return df
    
    def _resample_data(self, df: pd.DataFrame, period: str, current_date: pd.Timestamp) -> pd.DataFrame:
        """
        Resample daily data to weekly or monthly frequency.
        
        Args:
            df: DataFrame with daily data
            period: 'daily', 'weekly', or 'monthly'
            current_date: Current date for filtering
            
        Returns:
            Resampled DataFrame with dates <= current_date
        """
        if period == 'daily':
            # For daily, just reset index and filter
            df_reset = df.reset_index()
            df_reset = df_reset[df_reset['date'] <= current_date]
            return df_reset
        
        # Define resampling rule
        if period == 'weekly':
            rule = 'W-FRI'  # Weekly ending on Friday
        elif period == 'monthly':
            rule = 'ME'  # Month end
        else:
            raise ValueError(f"Unsupported period: {period}")
        
        # Define aggregation functions for required columns
        agg_dict = {
            'open': 'first',      # First trading day's open
            'close': 'last',      # Last trading day's close
            'high': 'max',        # Highest high during the period
            'low': 'min',         # Lowest low during the period
            'volume': 'sum',      # Total volume
            'change': 'last',     # Last period's absolute change
            'pct_change': 'last'  # Last period's percentage change
        }
        
        # Resample and aggregate
        resampled = df.resample(rule).agg(agg_dict)
        
        # Drop rows with NaN values (periods with no data)
        resampled = resampled.dropna()
        
        # Reset index to make date a column
        resampled.reset_index(inplace=True)
        
        # Filter to only include dates <= current_date
        resampled = resampled[resampled['date'] <= current_date]
        
        return resampled
    
    def _format_data_row(self, date: pd.Timestamp, row: pd.Series, period: str = "daily") -> str:
        """Format a single row of data into readable string."""
        date_str = date.strftime('%Y-%m-%d')
        
        # Build metrics list
        metrics = []
        
        # Add period label for non-daily data
        if period != 'daily':
            if period == 'weekly':
                metrics.append(f"[Weekly]")
            elif period == 'monthly':
                metrics.append(f"[Monthly]")
        
        # Include OHLC
        if 'open' in row and pd.notna(row['open']):
            metrics.append(f"Open={row['open']:.4f}")
        if 'high' in row and pd.notna(row['high']):
            metrics.append(f"High={row['high']:.4f}")
        if 'low' in row and pd.notna(row['low']):
            metrics.append(f"Low={row['low']:.4f}")
        if 'close' in row and pd.notna(row['close']):
            metrics.append(f"Close={row['close']:.4f}")
        
        # Volume
        if 'volume' in row and pd.notna(row['volume']):
            metrics.append(f"Volume={row['volume']:.0f}")
        
        # Price change metrics
        if 'pct_change' in row and pd.notna(row['pct_change']):
            metrics.append(f"PctChange={row['pct_change']:.4f}%")
        if 'change' in row and pd.notna(row['change']):
            metrics.append(f"Change={row['change']:+.4f}")
        
        return f"{date_str}: {', '.join(metrics)}"
    
    def get_implementation(self) -> Callable:
        def get_stock_data(symbol: str, length: int, period: str = "daily") -> str:
            """
            Get historical stock data for the specified symbol with flexible period sampling.
            
            Args:
                symbol: Stock code (e.g., 'AAPL')
                length: Number of past periods to retrieve (including current date)
                period: Sampling period - 'daily', 'weekly', or 'monthly' (default: 'daily')
                
            Returns:
                String containing formatted stock data
            """
            try:
                # Validate input
                if length <= 0:
                    return f"Error: length must be positive, got {length}"
                
                # Validate period
                if period not in ['daily', 'weekly', 'monthly']:
                    return f"Error: period must be 'daily', 'weekly', or 'monthly', got {period}"
                
                # Read date file to get current date
                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                
                if not current_date_str:
                    return "Error: current_date not found in date file"
                
                # Convert current date to datetime
                current_date = pd.to_datetime(current_date_str)
                
                # Load stock data
                df = self._load_stock_data(symbol.upper())
                
                # Filter data up to current_date
                mask = df.index <= current_date
                historical_data = df[mask].copy()
                
                if historical_data.empty:
                    return f"No data found for symbol {symbol} before or on {current_date_str}"
                
                # Resample data based on period
                resampled_data = self._resample_data(historical_data, period, current_date)
                
                if resampled_data.empty:
                    return f"No {period} data available for symbol {symbol}"
                
                # Sort by date descending to get recent to old, then take the last N periods
                resampled_data = resampled_data.sort_values('date', ascending=False)
                
                # Get the last N periods of data (including current date)
                period_data = resampled_data.head(length)
                
                # Format output
                period_names = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months'}
                period_name = period_names.get(period, 'periods')
                
                lines = []
                lines.append(f"Stock Data for {symbol} (last {len(period_data)} {period_name} up to {current_date_str}):")
                
                for idx, row in period_data.iterrows():
                    date = row['date']
                    lines.append(self._format_data_row(date, row, period))
                
                # Add summary section
                if len(period_data) > 1:
                    most_recent_close = period_data.iloc[0]['close']
                    oldest_close = period_data.iloc[-1]['close']
                    price_change = most_recent_close - oldest_close
                    pct_change = (price_change / oldest_close) * 100 if oldest_close != 0 else 0
                    
                    most_recent_date = period_data.iloc[0]['date']
                    oldest_date = period_data.iloc[-1]['date']
                    lines.append(f"Period: {oldest_date.strftime('%Y-%m-%d')} → {most_recent_date.strftime('%Y-%m-%d')}")
                    lines.append(f"Change: {price_change:+.4f} ({pct_change:+.4f}%)")
                    
                    # Add average volume
                    if 'volume' in period_data.columns:
                        avg_volume = period_data['volume'].mean()
                        lines.append(f"Avg Volume: {avg_volume:.0f}")
                
                return "\n".join(lines)
                
            except FileNotFoundError as e:
                return f"Error: {str(e)}"
            except Exception as e:
                return f"Error getting stock data: {str(e)}"
        
        return get_stock_data
    
    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """Return tool description based on the producer."""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Get historical stock data for a symbol including date, open, close, high, low, volume, change, and pct_change. Supports daily, weekly, and monthly sampling periods.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock code (e.g., 'AAPL')"
                        },
                        "length": {
                            "type": "integer",
                            "description": "Number of past periods to retrieve (including current date). For daily: number of trading days, for weekly: number of weeks, for monthly: number of months.",
                            "minimum": 1,
                            "maximum": 100
                        },
                        "period": {
                            "type": "string",
                            "description": "Sampling period - 'daily', 'weekly', or 'monthly'",
                            "enum": ["daily", "weekly", "monthly"],
                            "default": "daily"
                        }
                    },
                    "required": ["symbol", "length"]
                }
            }
        else:
            raise ValueError(f"Unsupported producer: {producer}")