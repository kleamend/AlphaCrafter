import json
import pandas as pd
import numpy as np
from datetime import datetime
import os

# Configuration
INITIAL_CAPITAL = 10000000
TRADING_DAYS_PER_YEAR = 243  # Number of trading days
BENCHMARK_ANNUAL_RETURN = 0.0125  # Benchmark annual return
BENCHMARK_DAILY_RETURN = (1 + BENCHMARK_ANNUAL_RETURN) ** (1 / TRADING_DAYS_PER_YEAR) - 1  # Daily compounded

def load_log_file(file_path):
    """Load JSON log file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def calculate_performance_metrics(account_snapshots, initial_capital):
    """
    Calculate performance metrics based on total assets
    
    Args:
        account_snapshots: list of account snapshots
        initial_capital: initial capital
    
    Returns:
        dictionary containing metrics and time series
    """
    dates = []
    total_assets_list = []

    # Extract date and total assets
    for snapshot in account_snapshots:
        date_str = snapshot.get('current_date', '')
        if not date_str and 'timestamp' in snapshot:
            date_str = snapshot['timestamp'].split()[0]

        account = snapshot.get('account', {})
        total_assets = account.get('total_assets', 0)

        dates.append(date_str)
        total_assets_list.append(total_assets)

    # Create time series
    returns_series = pd.Series(total_assets_list, index=pd.to_datetime(dates))
    daily_returns = returns_series.pct_change().dropna()

    # Total return
    total_return = (returns_series.iloc[-1] - initial_capital) / initial_capital

    # Time span
    total_days = len(returns_series)  # Number of days with returns (excluding the first day)
    
    # Annualized return (ARR - Absolute Return Ratio)
    if total_days > 0:
        annualized_return = (total_return + 1) ** (TRADING_DAYS_PER_YEAR / total_days) - 1
    else:
        annualized_return = 0

    # ============================================
    # Excess Return
    # ============================================
    # Simple excess return: strategy_return - benchmark_return
    excess_return = annualized_return - BENCHMARK_ANNUAL_RETURN
    excess_return_percent = excess_return * 100
    
    # Calculate excess daily returns (for volatility and Sharpe)
    # Assume benchmark daily return is constant (compounded daily)
    excess_daily_returns = daily_returns - BENCHMARK_DAILY_RETURN
    
    # Annualized excess volatility
    if len(excess_daily_returns) > 0:
        annualized_excess_volatility = excess_daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        annualized_excess_volatility = 0
    
    # Excess Sharpe Ratio (Information Ratio style)
    if annualized_excess_volatility > 0:
        excess_sharpe = excess_return / annualized_excess_volatility
    else:
        excess_sharpe = 0

    # Annualized volatility (absolute)
    if len(daily_returns) > 0:
        annualized_volatility = daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        annualized_volatility = 0

    # Original Sharpe ratio (for reference)
    if annualized_volatility > 0:
        sharpe_ratio = (annualized_return - BENCHMARK_ANNUAL_RETURN) / annualized_volatility
    else:
        sharpe_ratio = 0

    # Maximum drawdown
    cumulative_returns = returns_series / returns_series.iloc[0]
    rolling_max = cumulative_returns.expanding().max()
    drawdown = (cumulative_returns - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    # Maximum drawdown duration
    max_drawdown_duration = 0
    current_duration = 0
    in_drawdown = False

    for dd in drawdown:
        if dd < 0 and not in_drawdown:
            in_drawdown = True
            current_duration = 1
        elif dd < 0 and in_drawdown:
            current_duration += 1
        elif dd == 0 and in_drawdown:
            in_drawdown = False
            max_drawdown_duration = max(max_drawdown_duration, current_duration)
            current_duration = 0

    # Win rate
    positive_days = (daily_returns > 0).sum()
    negative_days = (daily_returns < 0).sum()
    win_rate = positive_days / len(daily_returns) if len(daily_returns) > 0 else 0

    # Profit/Loss ratio
    avg_win = daily_returns[daily_returns > 0].mean() if positive_days > 0 else 0
    avg_loss = abs(daily_returns[daily_returns < 0].mean()) if negative_days > 0 else 0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    return {
        'metrics': {
            'initial_capital': initial_capital,
            'final_assets': returns_series.iloc[-1],
            'total_return': total_return,
            'total_return_percent': total_return * 100,
            'annualized_return': annualized_return,
            'annualized_return_percent': annualized_return * 100,
            # Excess Return metrics (超额收益指标)
            'excess_return': excess_return,
            'excess_return_percent': excess_return_percent,
            'excess_sharpe': excess_sharpe,
            'annualized_excess_volatility': annualized_excess_volatility,
            'annualized_excess_volatility_percent': annualized_excess_volatility * 100,
            # Reference metrics
            'benchmark_annual_return': BENCHMARK_ANNUAL_RETURN,
            'benchmark_annual_return_percent': BENCHMARK_ANNUAL_RETURN * 100,
            'annualized_volatility': annualized_volatility,
            'annualized_volatility_percent': annualized_volatility * 100,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_percent': max_drawdown * 100,
            'max_drawdown_duration_days': max_drawdown_duration,
            'win_rate': win_rate,
            'win_rate_percent': win_rate * 100,
            'profit_loss_ratio': profit_loss_ratio,
            'total_days': total_days,
            'trading_days': len(daily_returns),
            'positive_days': positive_days,
            'negative_days': negative_days
        },
        'daily_returns': daily_returns,
        'excess_daily_returns': excess_daily_returns,
        'cumulative_returns': cumulative_returns,
        'dates': dates,
        'total_assets_list': total_assets_list
    }

def print_metrics(metrics):
    """Print performance report"""
    print("\n" + "="*60)
    print("Portfolio Performance Report")
    print("="*60)

    print(f"\nInitial Capital: ¥{metrics['initial_capital']:,.2f}")
    print(f"Final Assets: ¥{metrics['final_assets']:,.2f}")
    print(f"Total Return: {metrics['total_return_percent']:.2f}%")
    print(f"Total P&L: ¥{metrics['final_assets'] - metrics['initial_capital']:,.2f}")

    print("\n" + "-"*40)
    print("Absolute Performance (ARR)")
    print("-"*40)
    print(f"Annualized Return (ARR): {metrics['annualized_return_percent']:.2f}%")
    print(f"Annualized Volatility: {metrics['annualized_volatility_percent']:.2f}%")
    print(f"Benchmark Return: {metrics['benchmark_annual_return_percent']:.2f}%")

    print("\n" + "-"*40)
    print("Excess Performance (vs Benchmark)")
    print("-"*40)
    print(f"Excess Annualized Return: {metrics['excess_return_percent']:.2f}%")
    print(f"Excess Sharpe Ratio (Information Ratio): {metrics['excess_sharpe']:.4f}")
    print(f"Excess Volatility (Tracking Error): {metrics['annualized_excess_volatility_percent']:.2f}%")

    print("\n" + "-"*40)
    print("Drawdown Analysis")
    print("-"*40)
    print(f"Max Drawdown: {metrics['max_drawdown_percent']:.2f}%")
    print(f"Max Drawdown Duration: {metrics['max_drawdown_duration_days']} days")

    print("\n" + "-"*40)
    print("Trading Statistics")
    print("-"*40)
    print(f"Total Days: {metrics['total_days']} days")
    print(f"Trading Days: {metrics['trading_days']} days")
    print(f"Positive Days: {metrics['positive_days']} days")
    print(f"Negative Days: {metrics['negative_days']} days")
    print(f"Win Rate: {metrics['win_rate_percent']:.2f}%")
    print(f"Profit/Loss Ratio: {metrics['profit_loss_ratio']:.4f}")

    print("\n" + "="*60)

def main():
    """Main function"""
    input_file = 'sandbox/grid-live-a/logs/snapshot.json'

    if not os.path.exists(input_file):
        print(f"Error: file not found {input_file}")
        return

    print(f"Loading file: {input_file}")
    data = load_log_file(input_file)

    print("Calculating performance metrics...")
    result = calculate_performance_metrics(data, INITIAL_CAPITAL)

    print_metrics(result['metrics'])

    # Export to CSV
    df = pd.DataFrame({
        'date': result['cumulative_returns'].index,
        'total_assets': result['total_assets_list'],
        'cumulative_return': result['cumulative_returns'].values,
        'daily_return': result['daily_returns'].reindex(result['cumulative_returns'].index, fill_value=0),
        'excess_daily_return': result['excess_daily_returns'].reindex(result['cumulative_returns'].index, fill_value=0),
    })

if __name__ == "__main__":
    main()