"""
财务报表查询工具（GetFinancialStatementsTool）

功能概述：
    从本地 JSON 文件加载指定股票的财报数据（年报、季报、半年报等），
    按日期过滤并格式化为可读文本，供 LLM 进行基本面分析。

设计要点：
    - 内存缓存：同一标的的财报不重复读取
    - 时间窗口过滤：仅保留 <= current_date 的报告，可选回溯 N 年
    - 报表分组：按 report_type 分组（资产负债表 / 利润表 / 现金流量表等）
    - 数值格式化：大数加千分位、小数按精度输出
"""

from typing import Dict, Any, Callable, List, Optional
import json
import os
from pathlib import Path

from .base import BaseTool


class GetFinancialStatementsTool(BaseTool):
    """获取股票财务报表数据的工具。"""

    def __init__(self, dataset_dir_path: str = "../persistent/stock_financial_statements", date_file_path: str = "../persistent/date.json"):
        """初始化财报工具。

        参数:
            dataset_dir_path: 财报 JSON 文件目录。
            date_file_path:   当前日期 JSON 文件。
        """
        self.dataset_dir_path = dataset_dir_path
        self.date_file_path = date_file_path
        self.financials_cache: Dict[str, List[Dict]] = {}

    def get_name(self) -> str:
        """工具注册名。"""
        return "get_financial_statements"

    # ── 辅助方法 ───────────────────────────

    def _read_date_file(self) -> Dict[str, any]:
        """读取 date.json。"""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_stock_financials(self, symbol: str) -> List[Dict]:
        """从 JSON 加载财报，命中缓存直接返回。"""
        if symbol in self.financials_cache:
            return self.financials_cache[symbol]

        json_path = os.path.join(self.dataset_dir_path, f"{symbol}.json")
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Stock financial statements file not found: {json_path}")

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.financials_cache[symbol] = data
        return data

    def _filter_financials_by_date(self, financials: List[Dict], current_date: str, years: Optional[int] = None) -> List[Dict]:
        """过滤财报：
            - 必须 report_date <= current_date（已发布）
            - 若 years 指定，还需 report_date >= current_date - N 年
        返回按 report_date 降序排列的报告列表。
        """
        import pandas as pd
        current_date_obj = pd.to_datetime(current_date)

        cutoff_date = None
        if years is not None:
            cutoff_date = current_date_obj - pd.DateOffset(years=years)

        filtered_reports = []
        for report in financials:
            report_date = report.get('report_date')
            if report_date:
                report_date_obj = pd.to_datetime(report_date)
                if report_date_obj <= current_date_obj:
                    if cutoff_date is None or report_date_obj >= cutoff_date:
                        filtered_reports.append(report)

        filtered_reports.sort(key=lambda x: x.get('report_date', ''), reverse=True)
        return filtered_reports

    def _get_most_recent_by_type(self, reports: List[Dict]) -> List[Dict]:
        """同一 report_type 只保留最新的一份。"""
        reports_by_type = {}
        for report in reports:
            report_type = report.get('report_type')
            if report_type not in reports_by_type:
                reports_by_type[report_type] = report
        return list(reports_by_type.values())

    # ── 工具实现工厂 ───────────────────────────

    def get_implementation(self) -> Callable:
        def get_stock_financial_statements(symbol: str, years: Optional[int] = None) -> str:
            """查询一支股票的财报数据。

            参数:
                symbol: 股票代码。
                years:  回溯年数；None 表示返回所有已发布的报告。

            返回值:
                格式化的多行文本，按报表类型分组展示关键财务指标。
            """
            try:
                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                if not current_date_str:
                    return "Error: current_date not found in date file"

                financials = self._load_stock_financials(symbol)
                filtered_reports = self._filter_financials_by_date(financials, current_date_str, years)
                if not filtered_reports:
                    if years is not None:
                        return (
                            f"No financial statements found for symbol {symbol} "
                            f"in the last {years} year(s) (as of {current_date_str})"
                        )
                    return f"No financial statements found for symbol {symbol} before or on {current_date_str}"

                # 按 report_type 分组
                lines = [f"Financial Statements for {filtered_reports[0].get('company_name', symbol)} ({symbol})"]
                if years is not None:
                    lines.append(f"Data as of: {current_date_str} (Last {years} year{'s' if years > 1 else ''})")
                else:
                    lines.append(f"Data as of: {current_date_str} (All available reports)")
                lines.append("-" * 60)

                reports_by_type = {}
                for report in filtered_reports:
                    rtype = report.get('report_type', 'Unknown')
                    reports_by_type.setdefault(rtype, []).append(report)

                # 关键财务指标列表：(JSON 字段, 显示名称)
                metrics = [
                    ('currency', 'Currency'),
                    ('total_operating_revenue', 'Total Operating Revenue'),
                    ('net_profit_parent', 'Net Profit (Parent)'),
                    ('core_net_profit', 'Core Net Profit'),
                    ('weighted_roe', 'Weighted ROE'),
                    ('operating_cash_flow', 'Operating Cash Flow'),
                    ('investing_cash_flow', 'Investing Cash Flow'),
                    ('total_assets', 'Total Assets'),
                    ('cash_equivalent', 'Cash Equivalent'),
                    ('total_equity', 'Total Equity'),
                    ('parent_equity', 'Parent Equity'),
                    ('debt_to_asset_ratio', 'Debt to Asset Ratio'),
                    ('market_cap', 'Market Cap'),
                    ('shareholder_count', 'Shareholder Count'),
                    ('pe_ttm_core', 'PE-TTM (Core)'),
                    ('pb_ex_gw', 'PB (ex Goodwill)'),
                    ('dividend_yield', 'Dividend Yield'),
                    ('employee_count', 'Employee Count'),
                    ('audit_opinion', 'Audit Opinion'),
                    ('audit_firm', 'Audit Firm'),
                ]

                for rtype, reports in reports_by_type.items():
                    lines.append(f"\n{rtype}:")
                    for report in reports:
                        lines.append(f"  Report Date: {report.get('report_date', 'N/A')}")
                        for key, name in metrics:
                            if key in report and report[key] is not None:
                                value = report[key]
                                # 数值按量级自适应格式
                                if isinstance(value, (int, float)):
                                    if abs(value) > 1_000_000:
                                        lines.append(f"    {name}: {value:,.2f}")
                                    elif isinstance(value, float) and value != int(value):
                                        lines.append(f"    {name}: {value:.4f}")
                                    else:
                                        lines.append(f"    {name}: {value:,}")
                                else:
                                    lines.append(f"    {name}: {value}")
                        lines.append("")  # 报告间空行

                # 总结
                lines.append(f"\nTotal reports: {len(filtered_reports)}")
                lines.append(f"Report types: {', '.join(reports_by_type.keys())}")
                if years is not None:
                    lines.append(f"Date range: Last {years} year{'s' if years > 1 else ''} from {current_date_str}")

                return "\n".join(lines)

            except FileNotFoundError as e:
                return f"Error: {str(e)}"
            except json.JSONDecodeError as e:
                return f"Error parsing financial statements: {str(e)}"
            except Exception as e:
                import traceback
                traceback.print_exc()
                return f"Error getting stock financial statements: {str(e)}"

        return get_stock_financial_statements

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    "Get financial statements data for a stock symbol. "
                    "Returns reports from the specified number of years looking back from current_date."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock code",
                        },
                        "years": {
                            "type": "integer",
                            "description": (
                                "Number of years to look back from current_date. If not specified, "
                                "returns all available reports. If specified (e.g., 5), returns "
                                "reports from the last 5 years including current year."
                            ),
                            "minimum": 1,
                        },
                    },
                    "required": ["symbol"],
                },
            }
        raise ValueError(f"Unsupported producer: {producer}")
