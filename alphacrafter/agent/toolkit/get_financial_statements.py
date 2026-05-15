from typing import Dict, Any, Callable, List, Optional
import json
import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from .base import BaseTool


class GetFinancialStatementsTool(BaseTool):
    """Tool for getting financial statements data for a stock symbol."""
    
    def __init__(self, dataset_dir_path: str = "../persistent/stock_financial_statements", date_file_path: str = "../persistent/date.json"):
        """
        Initialize the get stock financials tool.
        
        Args:
            dataset_dir_path: Path to the folder containing stock financial JSON files
            date_file_path: Path to the date.json file containing current_date
        """
        self.dataset_dir_path = dataset_dir_path
        self.date_file_path = date_file_path
        
        # Cache for loaded data
        self.financials_cache: Dict[str, List[Dict]] = {}
    
    def get_name(self) -> str:
        return "get_financial_statements"
    
    def _read_date_file(self) -> Dict[str, any]:
        """Read and parse the date.json file."""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_stock_financials(self, symbol: str) -> List[Dict]:
        """Load stock financials from JSON file."""
        # Check cache first
        if symbol in self.financials_cache:
            return self.financials_cache[symbol]
        
        # Construct file path
        json_path = os.path.join(self.dataset_dir_path, f"{symbol}.json")
        
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Stock financial statements file not found: {json_path}")
        
        # Load JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Cache the data
        self.financials_cache[symbol] = data
        
        return data
    
    def _filter_financials_by_date(self, financials: List[Dict], current_date: str, years: Optional[int] = None) -> List[Dict]:
        """
        Filter financial statements to only include reports within the specified time window.
        
        Args:
            financials: The full financials data list
            current_date: The reference date string (YYYY-MM-DD)
            years: Number of years to look back from current_date. If None, return all reports up to current_date.
            
        Returns:
            Filtered financials list
        """
        current_date_obj = pd.to_datetime(current_date)
        
        # Calculate cutoff date if years is specified
        cutoff_date = None
        if years is not None:
            cutoff_date = current_date_obj - pd.DateOffset(years=years)
        
        filtered_reports = []
        for report in financials:
            report_date = report.get('report_date')
            if report_date:
                report_date_obj = pd.to_datetime(report_date)
                # Only include reports available before or on current_date
                if report_date_obj <= current_date_obj:
                    # If years is specified, also check if report is within the lookback period
                    if cutoff_date is None or report_date_obj >= cutoff_date:
                        filtered_reports.append(report)
        
        # Sort by date descending (newest first)
        filtered_reports.sort(key=lambda x: x.get('report_date', ''), reverse=True)
        
        return filtered_reports
    
    def _get_most_recent_by_type(self, reports: List[Dict]) -> List[Dict]:
        """
        Get only the most recent report for each report type.
        
        Args:
            reports: List of financial reports
            
        Returns:
            List with only the most recent report per type
        """
        # Group by report_type
        reports_by_type = {}
        for report in reports:
            report_type = report.get('report_type')
            if report_type not in reports_by_type:
                reports_by_type[report_type] = report
        
        return list(reports_by_type.values())
    
    def get_implementation(self) -> Callable:
        def get_stock_financial_statements(symbol: str, years: Optional[int] = None) -> str:
            """
            Get financial statements data for the specified symbol.
            
            Args:
                symbol: Stock code
                years: Number of years to look back from current_date. If None, return all available reports.
                       If specified, returns reports from the last N years (including current year).
                
            Returns:
                String containing formatted financial statements data
            """
            try:
                # Read date file to get current date
                date_data = self._read_date_file()
                current_date_str = date_data.get('current_date')
                
                if not current_date_str:
                    return "Error: current_date not found in date file"
                
                # Load stock financials
                financials = self._load_stock_financials(symbol)
                
                # Filter data based on years parameter
                filtered_reports = self._filter_financials_by_date(financials, current_date_str, years)
                
                if not filtered_reports:
                    if years is not None:
                        return f"No financial statements found for symbol {symbol} in the last {years} year(s) (as of {current_date_str})"
                    else:
                        return f"No financial statements found for symbol {symbol} before or on {current_date_str}"
                
                # Format output - return readable text
                lines = []
                lines.append(f"Financial Statements for {filtered_reports[0].get('company_name', symbol)} ({symbol})")
                
                if years is not None:
                    lines.append(f"Data as of: {current_date_str} (Last {years} year{'s' if years > 1 else ''})")
                else:
                    lines.append(f"Data as of: {current_date_str} (All available reports)")
                
                lines.append("-" * 60)
                
                # Group by report_type for display
                reports_by_type = {}
                for report in filtered_reports:
                    report_type = report.get('report_type', 'Unknown')
                    if report_type not in reports_by_type:
                        reports_by_type[report_type] = []
                    reports_by_type[report_type].append(report)
                
                for report_type, reports in reports_by_type.items():
                    if reports:
                        lines.append(f"\n{report_type}:")
                        for report in reports:
                            lines.append(f"  Report Date: {report.get('report_date', 'N/A')}")
                            
                            # List all key financial metrics
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
                                ('audit_firm', 'Audit Firm')
                            ]
                            
                            for field_key, field_name in metrics:
                                if field_key in report and report[field_key] is not None:
                                    value = report[field_key]
                                    # Format numbers
                                    if isinstance(value, (int, float)):
                                        if abs(value) > 1000000:
                                            lines.append(f"    {field_name}: {value:,.2f}")
                                        elif isinstance(value, float) and value != int(value):
                                            lines.append(f"    {field_name}: {value:.4f}")
                                        else:
                                            lines.append(f"    {field_name}: {value:,}")
                                    else:
                                        lines.append(f"    {field_name}: {value}")
                            
                            lines.append("")  # Empty line between reports
                
                # Add summary
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
        """Return tool description based on the producer."""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Get financial statements data for a stock symbol. Returns reports from the specified number of years looking back from current_date.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock code"
                        },
                        "years": {
                            "type": "integer",
                            "description": "Number of years to look back from current_date. If not specified, returns all available reports. If specified (e.g., 5), returns reports from the last 5 years including current year.",
                            "minimum": 1
                        }
                    },
                    "required": ["symbol"]
                }
            }
        else:
            raise ValueError(f"Unsupported producer: {producer}")