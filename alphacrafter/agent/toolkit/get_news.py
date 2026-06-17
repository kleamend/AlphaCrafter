"""
股票新闻查询工具（GetNewsTool）

功能概述：
    从本地 JSON 文件中加载指定股票或市场指数的新闻数据，
    按日期过滤后格式化为可读的多行文本，便于 LLM 进行情绪/事件分析。

设计要点：
    - 内存缓存：同一标的的 JSON 不重复读取
    - 时间窗口过滤：仅返回 <= current_date 且在 days 范围内的新闻
    - 摘要统计：聚合 sentiment / category 分布，便于快速评估市场情绪
    - 额外接口 get_implementation_raw：返回原始结构化数据，便于其它工具复用
"""

from typing import Dict, Any, Callable, List, Optional
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from .base import BaseTool


class GetNewsTool(BaseTool):
    """获取股票 / 指数新闻数据的工具。"""

    def __init__(self, dataset_dir_path: str = "../persistent/stock_news", date_file_path: str = "../persistent/date.json"):
        """初始化新闻工具。

        参数:
            dataset_dir_path: 新闻 JSON 文件目录。
            date_file_path:   当前日期 JSON 文件。
        """
        self.dataset_dir_path = dataset_dir_path
        self.date_file_path = date_file_path
        self.news_cache: Dict[str, List[Dict]] = {}  # 内存缓存：symbol -> 新闻列表

    def get_name(self) -> str:
        """工具注册名。"""
        return "get_news"

    # ── 辅助方法 ───────────────────────────

    def _read_date_file(self) -> Dict[str, any]:
        """读取 date.json。"""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_stock_news(self, symbol: str) -> List[Dict]:
        """从 JSON 加载新闻，命中缓存直接返回。"""
        if symbol in self.news_cache:
            return self.news_cache[symbol]

        json_path = os.path.join(self.dataset_dir_path, f"{symbol}.json")
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Stock news file not found: {json_path}")

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.news_cache[symbol] = data
        return data

    def _filter_news_by_date(self, news_list: List[Dict], current_date: str, days: int = 7) -> List[Dict]:
        """按日期过滤：仅保留在 (current_date - days, current_date] 区间内发布的新闻。

        排序按 publish_date 降序（最新在前）。
        """
        current_date_obj = datetime.strptime(current_date, '%Y-%m-%d')
        cutoff_date = current_date_obj - timedelta(days=days)

        filtered_news = []
        for news in news_list:
            publish_date_str = news.get('publish_date', '')
            if publish_date_str:
                # 兼容 "YYYY-MM-DD HH:MM:SS" 格式
                publish_date_obj = datetime.strptime(publish_date_str.split()[0], '%Y-%m-%d')
                if publish_date_obj <= current_date_obj and publish_date_obj >= cutoff_date:
                    filtered_news.append(news)

        filtered_news.sort(key=lambda x: x.get('publish_date', ''), reverse=True)
        return filtered_news

    def _format_news_item(self, news: Dict, index: int) -> str:
        """将单条新闻格式化为多行字符串。"""
        lines = [
            f"[{index}] {news.get('title', 'No Title')}",
            f"    Date: {news.get('publish_date', 'N/A')}",
            f"    Source: {news.get('source', 'N/A')}",
            f"    Category: {news.get('category', 'N/A')}",
            f"    Sentiment: {news.get('sentiment', 'N/A')}",
        ]
        if news.get('summary'):
            lines.append(f"    Summary: {news.get('summary')}")
        return "\n".join(lines)

    # ── 工具实现工厂 ───────────────────────────

    def get_implementation(self) -> Callable:
        def get_stock_news(symbol: str, days: int = 30) -> str:
            """查询一支股票 / 指数最近 N 天的新闻。

            参数:
                symbol: 股票或指数代码。
                days:   时间窗口（默认 30 天）。

            返回值:
                格式化的多行新闻列表 + 情绪/分类统计。
            """
            try:
                if days <= 0:
                    return f"Error: days must be positive, got {days}"

                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                if not current_date_str:
                    return "Error: current_date not found in date file"

                news_list = self._load_stock_news(symbol)
                filtered_news = self._filter_news_by_date(news_list, current_date_str, days)
                if not filtered_news:
                    return (
                        f"No news found for symbol {symbol} in the last {days} days "
                        f"(as of {current_date_str})"
                    )

                # 构造列表输出
                lines = [
                    f"News for {symbol} (last {len(filtered_news)} items, as of {current_date_str}):",
                    "-" * 80,
                ]
                for i, news in enumerate(filtered_news, 1):
                    lines.append(self._format_news_item(news, i))
                    lines.append("-" * 40)

                # 汇总 sentiment / category 分布
                sentiment_counts, category_counts = {}, {}
                for news in filtered_news:
                    sentiment = news.get('sentiment', 'unknown')
                    category = news.get('category', 'unknown')
                    sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
                    category_counts[category] = category_counts.get(category, 0) + 1

                lines.append("\nSummary:")
                lines.append(
                    f"  Sentiment: {', '.join([f'{k}={v}' for k, v in sentiment_counts.items()])}"
                )
                lines.append(
                    f"  Categories: {', '.join([f'{k}={v}' for k, v in category_counts.items()])}"
                )

                return "\n".join(lines)

            except FileNotFoundError as e:
                return f"Error: {str(e)}"
            except json.JSONDecodeError as e:
                return f"Error parsing news data: {str(e)}"
            except Exception as e:
                return f"Error getting stock news: {str(e)}"

        return get_stock_news

    # ── 原始数据接口（供其它工具复用） ───────────────────────────

    def get_implementation_raw(self) -> Callable:
        """返回未格式化的原始新闻列表（结构化数据），便于被其它工具直接消费。"""
        def get_stock_news_raw(symbol: str, days: int = 7) -> Optional[List[Dict]]:
            """获取原始新闻数据列表。

            参数:
                symbol: 股票或指数代码。
                days:   时间窗口（默认 7 天）。

            返回值:
                过滤后的新闻列表（无结果或异常时返回 None）。
            """
            try:
                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                if not current_date_str:
                    return None

                news_list = self._load_stock_news(symbol)
                filtered_news = self._filter_news_by_date(news_list, current_date_str, days)
                return filtered_news if filtered_news else None
            except Exception:
                return None

        return get_stock_news_raw

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    "Get news data for a stock symbol. Returns news items from the last N days "
                    "up to current_date. If an index code (e.g., 'SPX', '000300.SH') is provided, "
                    "returns broader market news including macroeconomic events, central bank "
                    "(e.g., Fed) announcements, and policy updates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock code",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of past days to retrieve news for (default: 30)",
                            "minimum": 1,
                            "default": 30,
                        },
                    },
                    "required": ["symbol"],
                },
            }
        raise ValueError(f"Unsupported producer: {producer}")
