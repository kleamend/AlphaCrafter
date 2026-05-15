from typing import Dict, Any, Callable, List, Optional
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from .base import BaseTool


class GetNewsTool(BaseTool):
    """Tool for getting news data for a stock symbol."""
    
    def __init__(self, dataset_dir_path: str = "../persistent/stock_news", date_file_path: str = "../persistent/date.json"):
        """
        Initialize the get stock news tool.
        
        Args:
            dataset_dir_path: Path to the folder containing stock news JSON files
            date_file_path: Path to the date.json file containing current_date
        """
        self.dataset_dir_path = dataset_dir_path
        self.date_file_path = date_file_path
        
        # Cache for loaded data
        self.news_cache: Dict[str, List[Dict]] = {}
    
    def get_name(self) -> str:
        return "get_news"
    
    def _read_date_file(self) -> Dict[str, any]:
        """Read and parse the date.json file."""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_stock_news(self, symbol: str) -> List[Dict]:
        """Load stock news from JSON file."""
        # Check cache first
        if symbol in self.news_cache:
            return self.news_cache[symbol]
        
        # Construct file path
        json_path = os.path.join(self.dataset_dir_path, f"{symbol}.json")
        
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Stock news file not found: {json_path}")
        
        # Load JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Cache the data
        self.news_cache[symbol] = data
        
        return data
    
    def _filter_news_by_date(self, news_list: List[Dict], current_date: str, days: int = 7) -> List[Dict]:
        """
        Filter news to only include items published before or on current_date,
        and within the specified number of days.
        
        Args:
            news_list: List of news items
            current_date: The cutoff date string (YYYY-MM-DD)
            days: Number of days to look back
            
        Returns:
            Filtered news list
        """
        current_date_obj = datetime.strptime(current_date, '%Y-%m-%d')
        cutoff_date = current_date_obj - timedelta(days=days)
        
        filtered_news = []
        for news in news_list:
            publish_date_str = news.get('publish_date', '')
            if publish_date_str:
                # Handle format like "2025-03-17 15:30:00"
                publish_date_obj = datetime.strptime(publish_date_str.split()[0], '%Y-%m-%d')
                # Only include news published before or on current_date and after cutoff
                if publish_date_obj <= current_date_obj and publish_date_obj >= cutoff_date:
                    filtered_news.append(news)
        
        # Sort by publish_date descending (newest first)
        filtered_news.sort(key=lambda x: x.get('publish_date', ''), reverse=True)
        
        return filtered_news
    
    def _format_news_item(self, news: Dict, index: int) -> str:
        """Format a single news item into readable string."""
        lines = []
        lines.append(f"[{index}] {news.get('title', 'No Title')}")
        lines.append(f"    Date: {news.get('publish_date', 'N/A')}")
        lines.append(f"    Source: {news.get('source', 'N/A')}")
        lines.append(f"    Category: {news.get('category', 'N/A')}")
        lines.append(f"    Sentiment: {news.get('sentiment', 'N/A')}")
        if news.get('summary'):
            lines.append(f"    Summary: {news.get('summary')}")
        return "\n".join(lines)
    
    def get_implementation(self) -> Callable:
        def get_stock_news(symbol: str, days: int = 30) -> str:
            """
            Get news data for the specified symbol.
            
            Args:
                symbol: Stock code
                days: Number of past days to retrieve news for (default: 7)
                
            Returns:
                String containing formatted news data
            """
            try:
                # Validate input
                if days <= 0:
                    return f"Error: days must be positive, got {days}"
                
                # Read date file to get current date
                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                
                if not current_date_str:
                    return "Error: current_date not found in date file"
                
                # Load stock news
                news_list = self._load_stock_news(symbol)
                
                # Filter news up to current_date and within days
                filtered_news = self._filter_news_by_date(news_list, current_date_str, days)
                
                if not filtered_news:
                    return f"No news found for symbol {symbol} in the last {days} days (as of {current_date_str})"
                
                # Format output
                lines = []
                lines.append(f"News for {symbol} (last {len(filtered_news)} items, as of {current_date_str}):")
                lines.append("-" * 80)
                
                for i, news in enumerate(filtered_news, 1):
                    lines.append(self._format_news_item(news, i))
                    lines.append("-" * 40)
                
                # Add summary
                sentiment_counts = {}
                category_counts = {}
                for news in filtered_news:
                    sentiment = news.get('sentiment', 'unknown')
                    category = news.get('category', 'unknown')
                    sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
                    category_counts[category] = category_counts.get(category, 0) + 1
                
                lines.append("\nSummary:")
                lines.append(f"  Sentiment: {', '.join([f'{k}={v}' for k, v in sentiment_counts.items()])}")
                lines.append(f"  Categories: {', '.join([f'{k}={v}' for k, v in category_counts.items()])}")
                
                return "\n".join(lines)
                
            except FileNotFoundError as e:
                return f"Error: {str(e)}"
            except json.JSONDecodeError as e:
                return f"Error parsing news data: {str(e)}"
            except Exception as e:
                return f"Error getting stock news: {str(e)}"
        
        return get_stock_news
    
    def get_implementation_raw(self) -> Callable:
        """
        Returns the raw news data without formatting.
        Useful for other tools that need to process the data.
        """
        def get_stock_news_raw(symbol: str, days: int = 7) -> Optional[List[Dict]]:
            """
            Get raw news data for the specified symbol.
            
            Args:
                symbol: Stock code
                days: Number of past days to retrieve news for (default: 7)
                
            Returns:
                List of filtered news items, or None if error
            """
            try:
                # Read date file to get current date
                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                
                if not current_date_str:
                    return None
                
                # Load stock news
                news_list = self._load_stock_news(symbol)
                
                # Filter news up to current_date and within days
                filtered_news = self._filter_news_by_date(news_list, current_date_str, days)
                
                return filtered_news if filtered_news else None
                
            except Exception:
                return None
        
        return get_stock_news_raw
    
    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """Return tool description based on the producer."""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Get news data for a stock symbol. Returns news items from the last N days up to current_date. If an index code (e.g., 'SPX', '000300.SH') is provided, returns broader market news including macroeconomic events, central bank (e.g., Fed) announcements, and policy updates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock code"
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of past days to retrieve news for (default: 30)",
                            "minimum": 1,
                            "default": 30
                        }
                    },
                    "required": ["symbol"]
                }
            }
        else:
            raise ValueError(f"Unsupported producer: {producer}")