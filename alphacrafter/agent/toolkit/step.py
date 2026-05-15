from typing import Dict, Any, Callable, List
import json
import os
import sys
from time import sleep
from pathlib import Path
from datetime import datetime
import numpy as np

from .base import BaseTool
from alphacrafter.sim.hook import Hook

class StepTool(BaseTool):
    def __init__(self, 
                 date_file_path: str = "../persistent/date.json", 
                 dataset_dir_path: str = "../persistent/stock_data", 
                 account_file_path: str = "../persistent/account.json", 
                 strategy_file_path: str = "./strategy.py",
                 log_file_path: str = "../logs/snapshot.json",
                 mode: str = "a"):
        """
        Initialize StepTool.
        
        Args:
            date_file_path: Path to date.json file
            dataset_dir_path: Path to stock data directory
            account_file_path: Path to account.json file
            strategy_file_path: Path to strategy.py file
            log_file_path: Path to snapshot.json log file
            mode: Market mode - "a" for A-share market, "us" for US stock market
        """
        self.date_file_path = date_file_path
        self.dataset_dir_path = dataset_dir_path
        self.account_file_path = account_file_path
        self.strategy_file_path = strategy_file_path
        self.log_file_path = log_file_path
        self.mode = mode.lower()
        
        # Import appropriate Exchange based on mode
        if self.mode == "a":
            from alphacrafter.sim.exchange_a import Exchange
        elif self.mode == "us":
            from alphacrafter.sim.exchange_us import Exchange
        else:
            raise ValueError(f"Unsupported mode: {mode}. Supported modes: 'a' (A-share), 'us' (US stock)")
        
        # Initialize exchange and hook
        self.exchange = Exchange(dataset_dir_path, account_file_path, date_file_path)
        self.hook = Hook(strategy_file_path)
        
        # Ensure log directory exists
        Path(self.log_file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize snapshot file as empty list if it doesn't exist
        self._init_snapshot_file()
        
        # Store snapshots for current step run
        self.step_snapshots = []

    def _init_snapshot_file(self) -> None:
        """Initialize snapshot file as empty list if it doesn't exist."""
        if not os.path.exists(self.log_file_path):
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                json.dump([], f, indent=2, ensure_ascii=False)

    def get_name(self) -> str:
        return "step"
    
    def _read_date_file(self) -> Dict[str, any]:
        """Read and parse the date.json file."""
        if not os.path.exists(self.date_file_path):
            raise FileNotFoundError(f"Date file not found: {self.date_file_path}")
        
        with open(self.date_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate required fields
        if 'current_date' not in data:
            raise ValueError("date.json missing 'current_date' field")
        if 'trading_days' not in data:
            raise ValueError("date.json missing 'trading_days' field")
        
        return data
    
    def _write_date_file(self, data: Dict[str, any]) -> None:
        """Write updated data back to date.json."""
        # Ensure directory exists
        Path(self.date_file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.date_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _read_account_file(self) -> str:
        """Read account file and return raw JSON string."""
        if not os.path.exists(self.account_file_path):
            return "{}"
        
        with open(self.account_file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _log_account_snapshot(self, date: str) -> None:
        """
        Log account snapshot as a JSON object appended to the list in snapshot.json.
        Also store in memory for metrics calculation.
        
        Format: {"timestamp": "YYYY-MM-DD HH:MM:SS", "current_date": "YYYY-MM-DD", "account": {...}}
        """
        try:
            # Read current account data
            account_data = self._read_account_file()
            account_dict = json.loads(account_data) if account_data != "{}" else {}
            account_dict["watch_list"] = []
            account_dict["orders"] = []
            account_dict["positions"] = []
            
            # Create snapshot
            snapshot = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "current_date": date,
                "account": account_dict
            }
            
            # Store in memory for metrics calculation
            self.step_snapshots.append({
                "date": date,
                "net_assets": account_dict.get("net_assets", 0.0),
                "total_assets": account_dict.get("total_assets", 0.0),
                "available_cash": account_dict.get("available_cash", 0.0),
                "market_value": account_dict.get("market_value", 0.0),
                "gross_position_rate": account_dict.get("gross_position_rate", 0.0),
                "net_position_rate": account_dict.get("net_position_rate", 0.0)
            })
            
            # Read existing snapshots
            if os.path.exists(self.log_file_path):
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    snapshots = json.load(f)
            else:
                snapshots = []
            
            # Append new snapshot
            snapshots.append(snapshot)
            
            # Write back to file
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                json.dump(snapshots, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Warning: Failed to log account snapshot: {e}")
    
    def _calculate_metrics(self) -> Dict[str, float]:
        """
        Calculate performance metrics from step snapshots.
        
        Returns:
            Dictionary with metrics:
            - Period Return (%)
            - Annualized Return (%)
            - Sharpe Ratio
            - Max Drawdown (%)
            - Calmar Ratio
            - Average Gross Position Rate (%)
            - Average Net Position Rate (%)
        """
        if len(self.step_snapshots) < 2:
            return {
                "Period Return (%)": 0.0,
                "Annualized Return (%)": 0.0,
                "Sharpe Ratio": 0.0,
                "Max Drawdown (%)": 0.0,
                "Calmar Ratio": 0.0,
                "Average Gross Position Rate (%)": 0.0,
                "Average Net Position Rate (%)": 0.0
            }
        
        # Extract net assets and position rates
        net_assets = [s["net_assets"] for s in self.step_snapshots]
        gross_position_rates = [s.get("gross_position_rate", 0.0) for s in self.step_snapshots]
        net_position_rates = [s.get("net_position_rate", 0.0) for s in self.step_snapshots]
        
        # Calculate daily returns
        daily_returns = []
        for i in range(1, len(net_assets)):
            if net_assets[i-1] > 0:
                daily_return = (net_assets[i] - net_assets[i-1]) / net_assets[i-1]
            else:
                daily_return = 0.0
            daily_returns.append(daily_return)
        
        if not daily_returns:
            return {
                "Period Return (%)": 0.0,
                "Annualized Return (%)": 0.0,
                "Sharpe Ratio": 0.0,
                "Max Drawdown (%)": 0.0,
                "Calmar Ratio": 0.0,
                "Average Gross Position Rate (%)": 0.0,
                "Average Net Position Rate (%)": 0.0
            }
        
        # Calculate metrics
        total_days = len(daily_returns)
        total_years = total_days / 240
        
        # Period Return
        initial_net_assets = net_assets[0]
        final_net_assets = net_assets[-1]
        period_return = (final_net_assets - initial_net_assets) / initial_net_assets if initial_net_assets > 0 else 0.0
        
        # Annualized Return
        if total_years > 0 and initial_net_assets > 0:
            annualized_return = (1 + period_return) ** (1 / total_years) - 1
        else:
            annualized_return = 0.0
        
        # Sharpe Ratio
        risk_free_rate = 0.0016
        daily_risk_free = risk_free_rate / 240
        excess_returns = [r - daily_risk_free for r in daily_returns]
        avg_excess_return = np.mean(excess_returns) if excess_returns else 0.0
        std_excess_return = np.std(excess_returns) if len(excess_returns) > 1 else 1e-6
        sharpe_ratio = (avg_excess_return / std_excess_return) * np.sqrt(240) if std_excess_return > 0 else 0.0
        
        # Max Drawdown
        peak = net_assets[0]
        max_drawdown = 0.0
        for value in net_assets:
            if value > peak:
                peak = value
            if peak > 0:
                drawdown = (peak - value) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        # Calmar Ratio
        calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0.0
        
        # Average Position Rates
        avg_gross_position_rate = np.mean(gross_position_rates) if gross_position_rates else 0.0
        avg_net_position_rate = np.mean(net_position_rates) if net_position_rates else 0.0
        
        return {
            "Period Return (%)": round(period_return * 100, 2),
            "Annualized Return (%)": round(annualized_return * 100, 2),
            "Sharpe Ratio": round(sharpe_ratio, 2),
            "Max Drawdown (%)": round(max_drawdown * 100, 2),
            "Calmar Ratio": round(calmar_ratio, 2),
            "Average Gross Position Rate (%)": round(avg_gross_position_rate * 100, 2),
            "Average Net Position Rate (%)": round(avg_net_position_rate * 100, 2)
        }
    
    def _find_next_trading_day(self, current_date: str, trading_days: List[str], steps: int) -> str:
        """
        Find the next trading day after moving forward by specified steps.
        
        Args:
            current_date: Current date string (YYYY-MM-DD)
            trading_days: List of all trading days
            steps: Number of steps to move forward
            
        Returns:
            Next trading date string (or last trading day if steps exceed bounds)
        """
        try:
            # Find index of current date
            current_idx = trading_days.index(current_date)
            
            # Calculate next index
            next_idx = current_idx + steps
            
            # If beyond bounds, return last element
            if next_idx >= len(trading_days):
                return trading_days[-1]
            
            return trading_days[next_idx]
            
        except ValueError as e:
            if "not in list" in str(e):
                raise ValueError(f"Current date {current_date} not found in trading days list")
            raise e
    
    def _order_results_to_string(self, results: List) -> str:
        """Convert OrderResultSchema list to string representation."""
        if not results:
            return ""
        
        lines = []
        for result in results:
            # Format timestamp
            timestamp = result.timestamp
            if hasattr(timestamp, 'strftime'):
                timestamp = timestamp.strftime('%Y-%m-%d')
            
            # Build result string with field:value format
            result_lines = []
            result_lines.append(f"order_id: {result.order_id}")
            result_lines.append(f"symbol: {result.symbol}")
            result_lines.append(f"order_type: {result.order_type}")
            result_lines.append(f"status: {result.status}")
            
            if result.message:
                result_lines.append(f"message: {result.message}")
            
            # Join with newlines and add separator between results
            lines.append("\n".join(result_lines))
        
        # Separate multiple results with a blank line
        return "\n\n".join(lines)
    
    def get_implementation(self) -> Callable:
        def step(days: int) -> str:
            """
            Advance the simulation by N trading days.
            
            Args:
                days: Number of trading days to advance
                
            Returns:
                String containing the results of the step execution, metrics, and raw account JSON
            """
            try:
                # Validate input            
                if days < 5:
                    days = 5
                    print(f"Starting step execution for {days} trading days...")
                
                # Reset snapshots for this run
                self.step_snapshots = []
                
                # Read current date state
                date_data = self._read_date_file()
                current_date_str = date_data['current_date']
                trading_days = date_data['trading_days']
                
                all_results = []
                next_date_str = current_date_str
                
                # Log initial account snapshot
                initial_account = self._read_account_file()
                account_dict = json.loads(initial_account) if initial_account != "{}" else {}
                self.step_snapshots.append({
                    "date": current_date_str,
                    "net_assets": account_dict.get("net_assets", 0.0),
                    "total_assets": account_dict.get("total_assets", 0.0),
                    "available_cash": account_dict.get("available_cash", 0.0),
                    "market_value": account_dict.get("market_value", 0.0),
                    "gross_position_rate": account_dict.get("gross_position_rate", 0.0),
                    "net_position_rate": account_dict.get("net_position_rate", 0.0)
                })
                
                # Process each day sequentially
                for i in range(days):
                    print(f"Processing day {i+1}/{days}...")
                    print(f"  Processing exchange pretick...")
                    self.exchange.pre_tick()
                    print(f"  ✓ Exchange pre tick processed")
                    sleep(0.4)
                    
                    print(f"  Executing strategy hook...")
                    self.hook.on_tick()
                    print(f"  ✓ Strategy hook executed")
                    sleep(0.4)

                    print(f"  Processing exchange tick...")
                    results = self.exchange.post_tick()
                    print(f"  ✓ Exchange post tick processed")
                    sleep(0.4)
                    
                    # Log account snapshot after exchange tick
                    self._log_account_snapshot(next_date_str)
                    print(f"  ✓ Account snapshot logged")
                    
                    # Collect results
                    day_result = {
                        "date": next_date_str,
                        "results": results
                    }
                    all_results.append(day_result)

                    next_date_str = self._find_next_trading_day(
                        next_date_str, 
                        trading_days, 
                        1
                    )
                    print(f"  Next trading day: {next_date_str}")

                    date_data['current_date'] = next_date_str
                    self._write_date_file(date_data)
                    print(f"  ✓ Date file updated")
                    sleep(0.4)      
                    
                    print(f"  Day {i+1} completed\n")
                
                # Calculate metrics from snapshots
                metrics = self._calculate_metrics()
                
                # Create output
                output_lines = []
                output_lines.append(f"Advanced {days} trading days: {current_date_str} → {next_date_str}")
                
                # Add metrics section
                if metrics.get("Period Return (%)", 0.0) != 0.0 or any(v != 0.0 for k, v in metrics.items() if "Position Rate" not in k):
                    output_lines.append("")
                    output_lines.append("📊 Performance Metrics:")
                    for metric_name, metric_value in metrics.items():
                        output_lines.append(f"  {metric_name}: {metric_value}")

                else:
                    output_lines.append("")
                    output_lines.append("No orders executed during this step.")
                
                return "\n".join(output_lines)
                
            except Exception as e:
                import traceback
                error_msg = f"Error during step execution: {str(e)}\n{traceback.format_exc()}"
                return error_msg
        
        return step
    
    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """
        Return tool description based on the producer.
        
        Args:
            producer: The model producer (currently supports "OpenAI")
                     Can be extended for other providers like Anthropic, Google, etc.
        """
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Advance the simulation by N trading days using the strategy defined in `workspace/strategy.py`. Returns performance metrics (Period Return, Annualized Return, Sharpe Ratio, Max Drawdown, Calmar Ratio, Average Position Rates), execution results, and account state.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of trading days to advance",
                            "minimum": 5,
                            "maximum": 10
                        }
                    },
                    "required": ["days"]
                }
            }
        else:
            raise ValueError(f"Unsupported producer: {producer}")