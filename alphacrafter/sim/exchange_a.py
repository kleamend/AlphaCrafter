import os
import json
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

from .schemas import AccountSchema, OrderSchema, OrderResultSchema, OrderStatus, OrderType, PositionData, PositionDirection


class Exchange:
    """
    Exchange simulator for backtesting trading strategies (A-share market)
    
    Handles order matching, account management, and data persistence
    Follows A-share rules: T+1 settlement, no short selling
    """
    
    def __init__(self, dataset_dir_path: str, account_file_path: str, date_file_path: str):
        """
        Initialize the exchange
        
        Args:
            dataset_dir_path: Path to the folder containing stock CSV files
            account_file_path: Path to the account file for persistence
            date_file_path: Path to the date.json file containing current_date and trading_days
            
        Raises:
            FileNotFoundError: If account file does not exist
        """
        self.dataset_dir_path = Path(dataset_dir_path)
        self.account_file_path = Path(account_file_path)
        self.date_file_path = Path(date_file_path)
        
        # Check if account file exists
        if not self.account_file_path.exists():
            raise FileNotFoundError(f"Account file not found: {account_file_path}")
        
        # Check if date file exists
        if not self.date_file_path.exists():
            raise FileNotFoundError(f"Date file not found: {date_file_path}")
        
        self.market_data: Dict[str, pd.DataFrame] = {}
        self.account: AccountSchema = None
        
        # Commission rate (A-share: typically 0.02%~0.03%)
        self.commission_rate = 0.0002

        # Load market data
        self._load_market_data()
    
    def _load_date_info(self) -> None:
        """Load date information from date.json"""
        with open(self.date_file_path, 'r') as f:
            date_data = json.load(f)
        
        self.current_date_str = date_data.get('current_date')
        self.trading_days = date_data.get('trading_days', [])
        
        if not self.current_date_str:
            raise ValueError("current_date not found in date.json")
        if not self.trading_days:
            raise ValueError("trading_days not found in date.json")
        
        self.current_date = datetime.strptime(self.current_date_str, "%Y-%m-%d")
        self.current_date = self.current_date.replace(hour=14, minute=30)
    
    def _get_previous_trading_day(self) -> Optional[str]:
        """Get the previous trading day from the trading_days list"""
        try:
            current_idx = self.trading_days.index(self.current_date_str)
            if current_idx > 0:
                return self.trading_days[current_idx - 1]
            return None
        except ValueError:
            return None
        
    def _load_market_data(self) -> None:
        """Load all CSV files from the dataset folder"""
        if not self.dataset_dir_path.exists():
            raise FileNotFoundError(f"Dataset path not found: {self.dataset_dir_path}")
        
        csv_files = self.dataset_dir_path.glob("*.csv")
        for csv_file in csv_files:
            try:
                # Extract stock code from filename (remove .csv)
                stock_code = csv_file.stem
                
                # Load CSV with proper date parsing (keep date as column, not index)
                df = pd.read_csv(csv_file)
                df['date'] = pd.to_datetime(df['date'])
                df.sort_values('date', inplace=True)  # Ensure sorted by date
                
                self.market_data[stock_code] = df
            except Exception as e:
                print(f"Error loading {csv_file}: {e}")
    
    def _load_account(self) -> AccountSchema:
        """Load account from JSON file with lock"""
        try:
            with open(self.account_file_path, 'r') as f:
                data = json.load(f)
            
            # Convert positions from list
            positions = []
            for pos_data in data.get('positions', []):
                # Ensure direction field exists (default to LONG for backward compatibility)
                if 'direction' not in pos_data:
                    pos_data['direction'] = PositionDirection.LONG
                positions.append(PositionData(**pos_data))
            
            # Convert orders
            orders = []
            for order_data in data.get('orders', []):
                # Convert string timestamps back to datetime
                if 'timestamp' in order_data and isinstance(order_data['timestamp'], str):
                    order_data['timestamp'] = datetime.fromisoformat(order_data['timestamp'])
                orders.append(OrderSchema(**order_data))
            

            return AccountSchema(
                total_assets=data.get('total_assets', 0),
                net_assets=data.get('net_assets', 0),
                available_cash=data.get('available_cash', 0),
                market_value=data.get('market_value', 0),
                total_profit_loss=data.get('total_profit_loss', 0),
                total_profit_loss_rate=data.get('total_profit_loss_rate', 0),
                gross_position_rate=data.get('gross_position_rate', 0),
                net_position_rate=data.get('net_position_rate', 0),
                positions=positions,
                orders=orders,
                watch_list=data.get('watch_list', []),
            )

        except Exception as e:
            raise RuntimeError(f"Failed to load account from {self.account_file_path}: {e}")
    
    def _save_account(self) -> None:
        """Save account to JSON file with lock and proper decimal formatting"""
        # Convert to dict for JSON serialization
        account_dict = self.account.model_dump()
        
        # Format decimal values
        # Percentages to 4 decimal places
        if 'total_profit_loss_rate' in account_dict:
            account_dict['total_profit_loss_rate'] = round(account_dict['total_profit_loss_rate'], 4)
        if 'gross_position_rate' in account_dict:
            account_dict['gross_position_rate'] = round(account_dict['gross_position_rate'], 4)
        if 'net_position_rate' in account_dict:
            account_dict['net_position_rate'] = round(account_dict['net_position_rate'], 4)
        
        # Other monetary values to 4 decimal places
        if 'total_assets' in account_dict:
            account_dict['total_assets'] = round(account_dict['total_assets'], 4)
        if 'net_assets' in account_dict:
            account_dict['net_assets'] = round(account_dict['net_assets'], 4)
        if 'available_cash' in account_dict:
            account_dict['available_cash'] = round(account_dict['available_cash'], 4)
        if 'market_value' in account_dict:
            account_dict['market_value'] = round(account_dict['market_value'], 4)
        if 'total_profit_loss' in account_dict:
            account_dict['total_profit_loss'] = round(account_dict['total_profit_loss'], 4)
        
        # Format positions
        for position in account_dict.get('positions', []):
            if 'cost_price' in position:
                position['cost_price'] = round(position['cost_price'], 4)
            if 'current_price' in position:
                position['current_price'] = round(position['current_price'], 4)
            if 'market_value' in position:
                position['market_value'] = round(position['market_value'], 4)
            if 'profit_loss' in position:
                position['profit_loss'] = round(position['profit_loss'], 4)
            if 'profit_loss_rate' in position:
                position['profit_loss_rate'] = round(position['profit_loss_rate'], 4)
            # Ensure direction is stored as string
            if 'direction' in position and hasattr(position['direction'], 'value'):
                position['direction'] = position['direction'].value
        
        # Format orders
        for order in account_dict.get('orders', []):
            if 'price' in order:
                order['price'] = round(order['price'], 4)
            
            # Convert datetime objects to strings
            if isinstance(order.get('timestamp'), datetime):
                order['timestamp'] = order['timestamp'].isoformat()
        
        # Ensure directory exists
        self.account_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.account_file_path, 'w') as f:
            json.dump(account_dict, f, indent=2, default=str)
    
    def _get_price_data(self, symbol: str, date: datetime) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Get price data for a symbol on a given date.
        If exact date not found, use the most recent historical data.
        
        Args:
            symbol: Stock code
            date: Trading date
            
        Returns:
            Tuple of (low_price, high_price, close_price) or (None, None, None) if no data found (suspended stock)
        """
        if symbol not in self.market_data:
            return None, None, None
        
        df = self.market_data[symbol]
        date_str = date.strftime('%Y-%m-%d')
        
        # Check if exact date exists
        exact_match = df[df['date'] == date_str]
        if not exact_match.empty:
            row = exact_match.iloc[0]
            return row['low'], row['high'], row['close']
        
        # If exact date not found, find the most recent date before the target date
        past_data = df[df['date'] < date_str]
        if not past_data.empty:
            # Get the most recent data
            latest_row = past_data.iloc[-1]
            print(f"Warning: No data for {symbol} on {date_str}, using data from {latest_row['date']}")
            return latest_row['low'], latest_row['high'], latest_row['close']
        
        # No data found - stock may be suspended or delisted
        print(f"Warning: No data found for {symbol} on {date_str} - stock may be suspended")
        return None, None, None
    
    def _find_position(self, symbol: str, direction: PositionDirection = PositionDirection.LONG) -> Optional[PositionData]:
        """Find position by symbol and direction in positions list"""
        for position in self.account.positions:
            if position.symbol == symbol and position.direction == direction:
                return position
        return None
    
    def _remove_position(self, symbol: str, direction: PositionDirection = PositionDirection.LONG) -> None:
        """Remove position by symbol and direction from positions list"""
        self.account.positions = [
            p for p in self.account.positions 
            if not (p.symbol == symbol and p.direction == direction)
        ]
    
    def _update_order_statuses(self) -> None:
        """
        Update order statuses based on age:
        - PENDING > 7 trading days → EXPIRED
        - Any order (PENDING/SUCCESS/FAILED/EXPIRED) > 14 trading days → removed
        """
        updated_orders = []
        
        for order in self.account.orders:
            # Find index of order date and current date in trading days list
            try:
                order_idx = self.trading_days.index(order.timestamp.strftime('%Y-%m-%d'))
                current_idx = self.trading_days.index(self.current_date_str)
                days_diff = current_idx - order_idx
            except ValueError:
                # If order date not in trading days, use calendar days as fallback
                days_diff = (self.current_date - order.timestamp).days
            
            if days_diff > 14:
                # Orders older than 14 trading days are removed (regardless of status)
                continue
            
            if order.status == OrderStatus.PENDING and days_diff > 7:
                # PENDING older than 7 trading days becomes EXPIRED
                order.status = OrderStatus.EXPIRED
                updated_orders.append(order)
            else:
                # Keep other orders
                updated_orders.append(order)
        
        self.account.orders = updated_orders
    
    def _update_account_metrics(self) -> None:
        """Update account metrics based on current positions and prices"""
        total_market_value = 0
        total_long_market_value = 0
        total_short_market_value = 0
        
        # Update each position with current price
        for position in self.account.positions:
            # Get current price
            _, _, current_price = self._get_price_data(position.symbol, self.current_date)
            
            if current_price is not None:
                # Update position with current price
                position.current_price = current_price
                position.market_value = position.quantity * current_price
                
                # Calculate profit/loss based on direction
                if position.direction == PositionDirection.LONG:
                    position.profit_loss = (current_price - position.cost_price) * position.quantity
                else:  # SHORT
                    position.profit_loss = (position.cost_price - current_price) * position.quantity
                
                # Calculate profit/loss rate
                if position.cost_price > 0 and position.quantity > 0:
                    cost_value = position.cost_price * position.quantity
                    position.profit_loss_rate = round(position.profit_loss / cost_value, 4)
                else:
                    position.profit_loss_rate = 0
                
                total_market_value += position.market_value
                if position.direction == PositionDirection.LONG:
                    total_long_market_value += position.market_value
                else:
                    total_short_market_value += position.market_value
            else:
                # Stock suspended - keep position with previous values
                total_market_value += position.market_value
                if position.direction == PositionDirection.LONG:
                    total_long_market_value += position.market_value
                else:
                    total_short_market_value += position.market_value
        
        # Update account metrics
        self.account.market_value = round(total_market_value, 4)
        
        # Net assets = available cash + total market value
        self.account.net_assets = round(self.account.available_cash + total_market_value, 4)
        self.account.total_assets = self.account.net_assets
        
        # Calculate total profit/loss based on total assets vs initial capital
        initial_capital = 10000000  # Initial capital is 10 million CNY
        
        # total_profit_loss = total_assets - initial_capital
        self.account.total_profit_loss = round(self.account.total_assets - initial_capital, 4)
        
        # total_profit_loss_rate = (total_assets - initial_capital) / initial_capital
        if initial_capital > 0:
            total_return = (self.account.total_assets - initial_capital) / initial_capital
            self.account.total_profit_loss_rate = round(total_return, 4)
        else:
            self.account.total_profit_loss_rate = 0
        
        # Gross position rate
        gross_exposure = sum(abs(p.market_value) for p in self.account.positions)
        self.account.gross_position_rate = round(gross_exposure / self.account.net_assets, 4) if self.account.net_assets > 0 else 0
        
        # Net position rate
        net_market_value = total_long_market_value - total_short_market_value
        self.account.net_position_rate = round(net_market_value / self.account.net_assets, 4) if self.account.net_assets > 0 else 0
    
    def _process_orders(self) -> List[OrderResultSchema]:
        """
        Process all pending orders and execute those that can be matched
        
        Returns:
            List of order results for orders that were processed (SUCCESS or FAILED)
        """
        results = []
        execution_time = self.current_date
        
        # Create a copy of orders list to avoid modification during iteration
        orders_to_process = list(self.account.orders)
        
        for order in orders_to_process:
            if order.status != OrderStatus.PENDING:
                continue
            
            # Get price data for the day
            low, high, close = self._get_price_data(order.symbol, self.current_date)
            
            if low is None or high is None:
                # No market data - order cannot be executed
                # Keep as PENDING for future days (stock might resume trading)
                print(f"Order {order.order_id}: Cannot execute - no market data for {order.symbol} (possibly suspended)")
                continue
            
            # Check if order price is within the day's range
            if low <= order.price <= high:
                # Order can be executed - use close price
                executed_price = close

                executed_amount = executed_price * order.quantity
                commission = round(executed_amount * self.commission_rate, 4)
                executed_amount = round(executed_amount, 4)
                
                # Process based on order type
                if order.order_type == OrderType.BUY:
                    total_cost = executed_amount + commission
                    
                    # Check if cash is sufficient
                    if self.account.available_cash >= total_cost:
                        # Update cash (immediately deducted)
                        self.account.available_cash = round(self.account.available_cash - total_cost, 4)
                        
                        # Find or create position (BUY always creates LONG position in A-share)
                        position = self._find_position(order.symbol, PositionDirection.LONG)
                        
                        if position:
                            # Update existing position
                            total_quantity = position.quantity + order.quantity
                            total_cost_value = (position.quantity * position.cost_price) + (order.quantity * executed_price)
                            position.cost_price = round(total_cost_value / total_quantity, 4)
                            position.quantity = total_quantity
                            # T+1: newly bought shares not available today
                            # available_quantity remains unchanged
                        else:
                            # Create new long position
                            new_position = PositionData(
                                symbol=order.symbol,
                                direction=PositionDirection.LONG,
                                quantity=order.quantity,
                                available_quantity=0,  # T+1: not available today
                                cost_price=executed_price,
                                current_price=executed_price,
                                market_value=executed_amount,
                                profit_loss=0,
                                profit_loss_rate=0
                            )
                            self.account.positions.append(new_position)
                        
                        # Update order status
                        order.status = OrderStatus.SUCCESS
                        
                        # Success result
                        results.append(OrderResultSchema(
                            order_id=order.order_id,
                            symbol=order.symbol,
                            order_type=order.order_type,
                            status=OrderStatus.SUCCESS,
                            timestamp=execution_time,
                            executed_quantity=order.quantity,
                            executed_price=executed_price,
                            executed_amount=executed_amount,
                            commission=commission
                        ))
                    else:
                        # Insufficient funds - failed
                        order.status = OrderStatus.FAILED
                        results.append(OrderResultSchema(
                            order_id=order.order_id,
                            symbol=order.symbol,
                            order_type=order.order_type,
                            status=OrderStatus.FAILED,
                            timestamp=execution_time,
                            executed_quantity=0,
                            executed_price=None,
                            executed_amount=0,
                            commission=0,
                            message="Insufficient funds"
                        ))
                    
                elif order.order_type == OrderType.SELL:
                    # In A-share, SELL always reduces LONG position (no short selling)
                    position = self._find_position(order.symbol, PositionDirection.LONG)
                    
                    # Check available shares (T+1: only shares bought before today are available)
                    if position and position.available_quantity >= order.quantity:
                        # Update cash (immediately added)
                        self.account.available_cash = round(self.account.available_cash + (executed_amount - commission), 4)
                        
                        # Update position - reduce available and total quantity
                        position.quantity -= order.quantity
                        position.available_quantity -= order.quantity
                        
                        # If position becomes zero, remove it
                        if position.quantity <= 0:
                            self._remove_position(order.symbol, PositionDirection.LONG)
                        
                        # Update order status
                        order.status = OrderStatus.SUCCESS
                        
                        # Success result
                        results.append(OrderResultSchema(
                            order_id=order.order_id,
                            symbol=order.symbol,
                            order_type=order.order_type,
                            status=OrderStatus.SUCCESS,
                            timestamp=execution_time,
                            executed_quantity=order.quantity,
                            executed_price=executed_price,
                            executed_amount=executed_amount,
                            commission=commission
                        ))
                    else:
                        # Insufficient shares - failed
                        order.status = OrderStatus.FAILED
                        results.append(OrderResultSchema(
                            order_id=order.order_id,
                            symbol=order.symbol,
                            order_type=order.order_type,
                            status=OrderStatus.FAILED,
                            timestamp=execution_time,
                            executed_quantity=0,
                            executed_price=None,
                            executed_amount=0,
                            commission=0,
                            message="Insufficient shares" + (" (T+1: shares not available yet)" if position and position.available_quantity < order.quantity else "")
                        ))
            else:
                # Price out of range for today - order remains PENDING for future days
                continue
        
        return results
    
    def _update_available_quantities(self) -> None:
        """
        Update available quantities based on T+1 rule:
        - Shares bought on the previous trading day become available today
        """
        # Get previous trading day
        prev_trading_day = self._get_previous_trading_day()
        if not prev_trading_day:
            return
        
        # Find all SUCCESS orders from previous trading day (BUY orders)
        for order in self.account.orders:
            if order.status == OrderStatus.SUCCESS and order.order_type == OrderType.BUY:
                # Check if order was executed on previous trading day
                if order.timestamp.strftime('%Y-%m-%d') == prev_trading_day:
                    # Make shares available (only for LONG positions)
                    position = self._find_position(order.symbol, PositionDirection.LONG)
                    if position:
                        # Add previous day's bought shares to available quantity
                        position.available_quantity += order.quantity
    
    def pre_tick(self) -> None:
        """
        Execute pre-tick settlement operations.
        Called before strategy execution to update settlement state.
        
        Operations:
        - Update available quantities for T+1 settlement
        - Update order statuses (PENDING -> EXPIRED after 7 days)
        - Remove old orders (>14 days)
        """
        self._load_date_info()
        self.account = self._load_account()
        
        # Update available quantities for T+1 settlement
        self._update_available_quantities()
        
        # Update order statuses using trading days
        self._update_order_statuses()
        
        # Update account metrics
        self._update_account_metrics()
        
        # Save updated state
        self._save_account()


    def post_tick(self) -> List[OrderResultSchema]:
        """
        Execute post-tick order matching.
        Called after strategy execution to match pending orders.
        
        Returns:
            List of order results for orders that were processed (SUCCESS or FAILED)
        """
        self._load_date_info()
        self.account = self._load_account()
        
        # Process pending orders
        execution_results = self._process_orders()
        
        # Update account metrics
        self._update_account_metrics()
        
        # Save updated state
        self._save_account()
        
        return execution_results