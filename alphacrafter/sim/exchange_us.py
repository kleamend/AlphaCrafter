"""
美股仿真撮合引擎（Exchange）

功能概述：
    与 A 股版同结构，但遵循美股市场规则：
      - T+0 结算：当日买入即可卖出
      - 支持做空：SELL 可在无持仓时直接开 SHORT
      - 撮合时间：每个交易日 16:00（仿真时钟统一为该时刻）
      - 撮合价：当日 close 价（在 low~high 区间内才成交）
      - 订单时效：PENDING > 7 个交易日自动 EXPIRED；> 14 个交易日被移除
      - 手续费率：0.01%
      - 引入保证金机制：short 头寸需 20% 初始保证金；净值跌破 80% 触发强平

数据流（每日循环）与 A 股版基本相同，差别主要在：
  - _process_orders: 支持"买平 SHORT"与"卖开 SHORT"
  - _check_margin_call: 在 post_tick 中检测保证金并强制平仓
"""

import os
import json
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

from .schemas import (
    AccountSchema, OrderSchema, OrderResultSchema,
    OrderStatus, OrderType, PositionData, PositionDirection,
)


class Exchange:
    """美股仿真撮合引擎。"""

    def __init__(self, dataset_dir_path: str, account_file_path: str, date_file_path: str):
        """初始化美股 Exchange。

        参数:
            dataset_dir_path: 股票 CSV 文件目录。
            account_file_path: 账户 JSON 文件。
            date_file_path:    date.json 文件。

        异常:
            FileNotFoundError: 账户或 date.json 不存在。
        """
        self.dataset_dir_path = Path(dataset_dir_path)
        self.account_file_path = Path(account_file_path)
        self.date_file_path = Path(date_file_path)

        if not self.account_file_path.exists():
            raise FileNotFoundError(f"Account file not found: {account_file_path}")
        if not self.date_file_path.exists():
            raise FileNotFoundError(f"Date file not found: {date_file_path}")

        self.market_data: Dict[str, pd.DataFrame] = {}
        self.account: AccountSchema = None

        # ── 美股手续费率与保证金参数 ──
        self.commission_rate = 0.0001         # 0.01%
        self.short_margin_requirement = 0.2   # 开空仓需 20% 初始保证金
        self.maintenance_margin = 0.8         # 净值 < 80% * 保证金需求 -> 强平
        self.short_interest_rate = 0.0        # 简化实现：不计空头利息

        self._load_market_data()

    # ── 日期 / 行情 加载 ───────────────────────────

    def _load_date_info(self) -> None:
        """读取 date.json；仿真时钟统一指向 16:00 美东收盘。"""
        with open(self.date_file_path, 'r') as f:
            date_data = json.load(f)

        self.current_date_str = date_data.get('current_date')
        self.trading_days = date_data.get('trading_days', [])

        if not self.current_date_str:
            raise ValueError("current_date not found in date.json")
        if not self.trading_days:
            raise ValueError("trading_days not found in date.json")

        self.current_date = datetime.strptime(self.current_date_str, "%Y-%m-%d")
        self.current_date = self.current_date.replace(hour=16, minute=0)

    def _get_previous_trading_day(self) -> Optional[str]:
        """取 trading_days 列表中的前一个交易日。"""
        try:
            current_idx = self.trading_days.index(self.current_date_str)
            if current_idx > 0:
                return self.trading_days[current_idx - 1]
            return None
        except ValueError:
            return None

    def _load_market_data(self) -> None:
        """加载数据集目录下所有股票 CSV。"""
        if not self.dataset_dir_path.exists():
            raise FileNotFoundError(f"Dataset path not found: {self.dataset_dir_path}")

        csv_files = self.dataset_dir_path.glob("*.csv")
        for csv_file in csv_files:
            try:
                stock_code = csv_file.stem
                df = pd.read_csv(csv_file)
                df['date'] = pd.to_datetime(df['date'])
                df.sort_values('date', inplace=True)
                self.market_data[stock_code] = df
            except Exception as e:
                print(f"Error loading {csv_file}: {e}")

    # ── 账户加载 / 持久化 ───────────────────────────

    def _load_account(self) -> AccountSchema:
        """从 JSON 反序列化为 Pydantic 对象。"""
        try:
            with open(self.account_file_path, 'r') as f:
                data = json.load(f)

            positions = []
            for pos_data in data.get('positions', []):
                # 老数据兼容：缺 direction 字段时默认 LONG
                if 'direction' not in pos_data:
                    pos_data['direction'] = PositionDirection.LONG
                positions.append(PositionData(**pos_data))

            orders = []
            for order_data in data.get('orders', []):
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
        """账户对象 -> JSON。

        美股特有：SHORT 持仓的 quantity / available_quantity 在磁盘上为负数。
        """
        account_dict = self.account.model_dump()

        # 比例字段精度
        for field in ['total_profit_loss_rate', 'gross_position_rate', 'net_position_rate']:
            if field in account_dict:
                account_dict[field] = round(account_dict[field], 4)

        # 资金字段精度
        for field in ['total_assets', 'net_assets', 'available_cash', 'market_value', 'total_profit_loss']:
            if field in account_dict:
                account_dict[field] = round(account_dict[field], 4)

        # 持仓字段：注意 SHORT 在磁盘上以负数存储
        for position in account_dict.get('positions', []):
            for field in ['cost_price', 'current_price', 'market_value', 'profit_loss', 'profit_loss_rate']:
                if field in position:
                    position[field] = round(position[field], 4)
            if 'direction' in position and hasattr(position['direction'], 'value'):
                position['direction'] = position['direction'].value
            # 美股约定：SHORT 持仓的数量在磁盘中为负
            if position.get('direction') == 'SHORT' and position.get('quantity', 0) > 0:
                position['quantity'] = -position['quantity']
            if position.get('direction') == 'SHORT' and position.get('available_quantity', 0) > 0:
                position['available_quantity'] = -position['available_quantity']

        # 订单字段
        for order in account_dict.get('orders', []):
            if 'price' in order:
                order['price'] = round(order['price'], 4)
            if isinstance(order.get('timestamp'), datetime):
                order['timestamp'] = order['timestamp'].isoformat()

        self.account_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.account_file_path, 'w') as f:
            json.dump(account_dict, f, indent=2, default=str)

    # ── 行情查询 ───────────────────────────

    def _get_price_data(self, symbol: str, date: datetime) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """取 (low, high, close)，缺数据时回退到最近历史日。"""
        if symbol not in self.market_data:
            return None, None, None

        df = self.market_data[symbol]
        date_str = date.strftime('%Y-%m-%d')

        exact_match = df[df['date'] == date_str]
        if not exact_match.empty:
            row = exact_match.iloc[0]
            return row['low'], row['high'], row['close']

        past_data = df[df['date'] < date_str]
        if not past_data.empty:
            latest_row = past_data.iloc[-1]
            print(f"Warning: No data for {symbol} on {date_str}, using data from {latest_row['date']}")
            return latest_row['low'], latest_row['high'], latest_row['close']

        print(f"Warning: No data found for {symbol} on {date_str} - stock may be suspended")
        return None, None, None

    # ── 持仓操作 ───────────────────────────

    def _find_position(self, symbol: str, direction: PositionDirection) -> Optional[PositionData]:
        """按 (symbol, direction) 查持仓。"""
        for position in self.account.positions:
            if position.symbol == symbol and position.direction == direction:
                return position
        return None

    def _remove_position(self, symbol: str, direction: PositionDirection) -> None:
        """从账户中移除指定 (symbol, direction) 持仓。"""
        self.account.positions = [
            p for p in self.account.positions
            if not (p.symbol == symbol and p.direction == direction)
        ]

    # ── 保证金计算 ───────────────────────────

    def _calculate_margin_requirement(self) -> float:
        """计算所有 SHORT 头寸所需的初始保证金合计（多头不需要保证金）。"""
        total_margin = 0.0
        for position in self.account.positions:
            if position.direction == PositionDirection.SHORT:
                total_margin += abs(position.market_value) * self.short_margin_requirement
        return total_margin

    def _calculate_equity(self) -> float:
        """账户权益 = 现金 + 各持仓市值（SHORT 市值为负）。"""
        total_market_value = sum(p.market_value for p in self.account.positions)
        return self.account.available_cash + total_market_value

    def _check_margin_call(self) -> List[OrderResultSchema]:
        """保证金检查 + 强制平仓。

        触发条件: 净值 < 维持保证金（= 保证金需求 * maintenance_margin）。
        强平顺序：先 SHORT（按亏损最大优先），再 LONG；
        每平一笔就重算一次净值，直到满足要求。
        """
        liquidation_results = []

        equity = self._calculate_equity()
        margin_requirement = self._calculate_margin_requirement()
        required_equity = margin_requirement * self.maintenance_margin

        if equity < required_equity and margin_requirement > 0:
            print(f"Margin call triggered! Equity: {equity:.2f}, Required: {required_equity:.2f}")

            positions_to_liquidate = []
            # 优先平亏损最大的 SHORT
            short_positions = [p for p in self.account.positions if p.direction == PositionDirection.SHORT]
            long_positions = [p for p in self.account.positions if p.direction == PositionDirection.LONG]
            short_positions.sort(key=lambda p: p.profit_loss)
            positions_to_liquidate.extend(short_positions)
            positions_to_liquidate.extend(long_positions)

            for position in positions_to_liquidate:
                if equity >= required_equity:
                    break

                _, _, current_price = self._get_price_data(position.symbol, self.current_date)
                if current_price is None:
                    # 停牌无法强平
                    continue

                abs_quantity = abs(position.quantity)
                executed_amount = current_price * abs_quantity
                commission = round(executed_amount * self.commission_rate, 4)

                if position.direction == PositionDirection.LONG:
                    # 强平多头：现金增加（成交额 - 手续费）
                    self.account.available_cash += (executed_amount - commission)
                    position.quantity = 0
                    liquidation_results.append(OrderResultSchema(
                        order_id=f"MARGIN_LIQUIDATION_{position.symbol}",
                        symbol=position.symbol,
                        order_type=OrderType.SELL,
                        status=OrderStatus.SUCCESS,
                        timestamp=self.current_date,
                        executed_quantity=abs_quantity,
                        executed_price=current_price,
                        executed_amount=executed_amount,
                        commission=commission,
                        message="Margin call: forced liquidation",
                    ))
                else:  # SHORT
                    # 强平空头：买入回补，现金减少
                    self.account.available_cash -= (executed_amount + commission)
                    position.quantity = 0
                    liquidation_results.append(OrderResultSchema(
                        order_id=f"MARGIN_LIQUIDATION_{position.symbol}",
                        symbol=position.symbol,
                        order_type=OrderType.BUY,
                        status=OrderStatus.SUCCESS,
                        timestamp=self.current_date,
                        executed_quantity=abs_quantity,
                        executed_price=current_price,
                        executed_amount=executed_amount,
                        commission=commission,
                        message="Margin call: forced liquidation",
                    ))

                self._remove_position(position.symbol, position.direction)
                equity = self._calculate_equity()

            if equity < 0:
                # 极端情况：即使全部平仓也不够 -> 破产
                print(f"Account bankrupt! Equity: {equity:.2f}")
                liquidation_results.append(OrderResultSchema(
                    order_id="BANKRUPTCY",
                    symbol="",
                    order_type=None,
                    status=OrderStatus.FAILED,
                    timestamp=self.current_date,
                    executed_quantity=0,
                    executed_price=None,
                    executed_amount=0,
                    commission=0,
                    message="Account bankrupt due to margin call",
                ))

        return liquidation_results

    # ── 订单生命周期 ───────────────────────────

    def _update_order_statuses(self) -> None:
        """按订单年龄推进状态（PENDING > 7 -> EXPIRED；> 14 -> 删除）。"""
        updated_orders = []

        for order in self.account.orders:
            try:
                order_idx = self.trading_days.index(order.timestamp.strftime('%Y-%m-%d'))
                current_idx = self.trading_days.index(self.current_date_str)
                days_diff = current_idx - order_idx
            except ValueError:
                days_diff = (self.current_date - order.timestamp).days

            if days_diff > 14:
                continue

            if order.status == OrderStatus.PENDING and days_diff > 7:
                order.status = OrderStatus.EXPIRED
                updated_orders.append(order)
            else:
                updated_orders.append(order)

        self.account.orders = updated_orders

    # ── 账户指标 ───────────────────────────

    def _update_account_metrics(self) -> None:
        """用最新价格刷新每个持仓的市值 / P&L / 盈亏比，并汇总账户层指标。

        美股特有：SHORT 持仓的 quantity 为负，市值 = quantity * price（也变负）。
        """
        total_market_value = 0
        total_long_market_value = 0
        total_short_market_value = 0

        for position in self.account.positions:
            _, _, current_price = self._get_price_data(position.symbol, self.current_date)

            if current_price is not None:
                position.current_price = current_price
                position.market_value = position.quantity * current_price

                if position.direction == PositionDirection.LONG:
                    position.profit_loss = (current_price - position.cost_price) * position.quantity
                else:  # SHORT
                    position.profit_loss = (position.cost_price - current_price) * abs(position.quantity)

                if position.cost_price > 0 and position.quantity != 0:
                    cost_value = abs(position.cost_price * position.quantity)
                    position.profit_loss_rate = round(position.profit_loss / cost_value, 4)
                else:
                    position.profit_loss_rate = 0

                total_market_value += position.market_value
                if position.direction == PositionDirection.LONG:
                    total_long_market_value += position.market_value
                else:
                    total_short_market_value += position.market_value
            else:
                # 停牌：保持原值
                total_market_value += position.market_value
                if position.direction == PositionDirection.LONG:
                    total_long_market_value += position.market_value
                else:
                    total_short_market_value += position.market_value

        self.account.market_value = round(total_market_value, 4)
        self.account.net_assets = round(self.account.available_cash + total_market_value, 4)
        self.account.total_assets = self.account.net_assets

        initial_capital = 10_000_000  # 美股初始资金 1000 万 USD
        self.account.total_profit_loss = round(self.account.total_assets - initial_capital, 4)
        if initial_capital > 0:
            self.account.total_profit_loss_rate = round(
                (self.account.total_assets - initial_capital) / initial_capital, 4
            )
        else:
            self.account.total_profit_loss_rate = 0

        gross_exposure = sum(abs(p.market_value) for p in self.account.positions)
        self.account.gross_position_rate = (
            round(gross_exposure / self.account.net_assets, 4)
            if self.account.net_assets != 0 else 0
        )

        net_exposure = total_long_market_value + total_short_market_value
        self.account.net_position_rate = (
            round(net_exposure / self.account.net_assets, 4)
            if self.account.net_assets != 0 else 0
        )

    # ── 订单撮合 ───────────────────────────

    def _process_orders(self) -> List[OrderResultSchema]:
        """对所有 PENDING 订单尝试撮合。

        美股撮合逻辑要点：
          - BUY 优先用于"回补 SHORT"（cover），剩余量才建 LONG
          - SELL 优先用于"平 LONG"，剩余量才开 SHORT
          - SHORT 头寸在内存中 quantity 为负，磁盘中亦为负
        """
        results = []
        execution_time = self.current_date

        orders_to_process = list(self.account.orders)

        for order in orders_to_process:
            if order.status != OrderStatus.PENDING:
                continue

            low, high, close = self._get_price_data(order.symbol, self.current_date)
            if low is None or high is None:
                print(f"Order {order.order_id}: Cannot execute - no market data for {order.symbol}")
                continue

            if not (low <= order.price <= high):
                continue

            executed_price = close
            executed_amount = executed_price * order.quantity
            commission = round(executed_amount * self.commission_rate, 4)
            executed_amount = round(executed_amount, 4)

            if order.order_type == OrderType.BUY:
                # ── BUY 优先 cover SHORT ──
                short_position = self._find_position(order.symbol, PositionDirection.SHORT)

                if short_position and short_position.quantity < 0:
                    abs_short_quantity = abs(short_position.quantity)
                    cover_quantity = min(order.quantity, abs_short_quantity)

                    # 平仓盈亏 = (成本 - 买入价) * 数量
                    cover_profit = (short_position.cost_price - executed_price) * cover_quantity

                    # 现金变动：减去回补花费 + 手续费
                    cash_change = -(executed_price * cover_quantity + commission)
                    self.account.available_cash = round(self.account.available_cash + cash_change, 4)

                    # SHORT 数量变 0 即平仓（quantity 向 0 方向加）
                    short_position.quantity += cover_quantity
                    short_position.profit_loss += cover_profit

                    if short_position.quantity >= 0:
                        self._remove_position(order.symbol, PositionDirection.SHORT)

                    if cover_quantity == order.quantity:
                        # 全部回补：BUY 完成
                        order.status = OrderStatus.SUCCESS
                        results.append(OrderResultSchema(
                            order_id=order.order_id,
                            symbol=order.symbol,
                            order_type=order.order_type,
                            status=OrderStatus.SUCCESS,
                            timestamp=execution_time,
                            executed_quantity=cover_quantity,
                            executed_price=executed_price,
                            executed_amount=executed_price * cover_quantity,
                            commission=commission,
                            message="Covered short position",
                        ))
                        continue
                    else:
                        # 部分回补 -> 剩余数量继续建 LONG
                        remaining_quantity = order.quantity - cover_quantity
                        results.append(OrderResultSchema(
                            order_id=f"{order.order_id}",
                            symbol=order.symbol,
                            order_type=order.order_type,
                            status=OrderStatus.SUCCESS,
                            timestamp=execution_time,
                            executed_quantity=cover_quantity,
                            executed_price=executed_price,
                            executed_amount=executed_price * cover_quantity,
                            commission=round(executed_price * cover_quantity * self.commission_rate, 4),
                            message="Partially covered short position",
                        ))
                        order.quantity = remaining_quantity
                        executed_amount = executed_price * remaining_quantity
                        commission = round(executed_amount * self.commission_rate, 4)

                # ── BUY 建/加 LONG ──
                total_cost = executed_amount + commission
                if self.account.available_cash >= total_cost:
                    self.account.available_cash = round(self.account.available_cash - total_cost, 4)

                    long_position = self._find_position(order.symbol, PositionDirection.LONG)
                    if long_position:
                        total_quantity = long_position.quantity + order.quantity
                        total_cost_value = (
                            long_position.quantity * long_position.cost_price
                            + order.quantity * executed_price
                        )
                        long_position.cost_price = round(total_cost_value / total_quantity, 4)
                        long_position.quantity = total_quantity
                    else:
                        # T+0：建仓即用
                        new_position = PositionData(
                            symbol=order.symbol,
                            direction=PositionDirection.LONG,
                            quantity=order.quantity,
                            available_quantity=order.quantity,
                            cost_price=executed_price,
                            current_price=executed_price,
                            market_value=executed_amount,
                            profit_loss=0,
                            profit_loss_rate=0,
                        )
                        self.account.positions.append(new_position)

                    order.status = OrderStatus.SUCCESS
                    results.append(OrderResultSchema(
                        order_id=order.order_id,
                        symbol=order.symbol,
                        order_type=order.order_type,
                        status=OrderStatus.SUCCESS,
                        timestamp=execution_time,
                        executed_quantity=order.quantity,
                        executed_price=executed_price,
                        executed_amount=executed_amount,
                        commission=commission,
                    ))
                else:
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
                        message="Insufficient funds",
                    ))

            elif order.order_type == OrderType.SELL:
                # ── SELL 优先平 LONG ──
                long_position = self._find_position(order.symbol, PositionDirection.LONG)

                if long_position and long_position.quantity > 0:
                    sell_quantity = min(order.quantity, long_position.quantity)
                    sell_profit = (executed_price - long_position.cost_price) * sell_quantity

                    self.account.available_cash = round(
                        self.account.available_cash + (executed_price * sell_quantity - commission), 4
                    )

                    long_position.quantity -= sell_quantity
                    long_position.profit_loss += sell_profit

                    if long_position.quantity <= 0:
                        self._remove_position(order.symbol, PositionDirection.LONG)

                    if sell_quantity == order.quantity:
                        order.status = OrderStatus.SUCCESS
                        results.append(OrderResultSchema(
                            order_id=order.order_id,
                            symbol=order.symbol,
                            order_type=order.order_type,
                            status=OrderStatus.SUCCESS,
                            timestamp=execution_time,
                            executed_quantity=sell_quantity,
                            executed_price=executed_price,
                            executed_amount=executed_price * sell_quantity,
                            commission=commission,
                            message="Closed long position",
                        ))
                        continue
                    else:
                        # 部分平仓 -> 剩余数量开 SHORT
                        remaining_quantity = order.quantity - sell_quantity
                        results.append(OrderResultSchema(
                            order_id=f"{order.order_id}",
                            symbol=order.symbol,
                            order_type=order.order_type,
                            status=OrderStatus.SUCCESS,
                            timestamp=execution_time,
                            executed_quantity=sell_quantity,
                            executed_price=executed_price,
                            executed_amount=executed_price * sell_quantity,
                            commission=round(executed_price * sell_quantity * self.commission_rate, 4),
                            message="Partially closed long position",
                        ))
                        order.quantity = remaining_quantity
                        executed_amount = executed_price * remaining_quantity
                        commission = round(executed_amount * self.commission_rate, 4)

                # ── SELL 开/加 SHORT：现金增加（卖出收入） ──
                self.account.available_cash = round(
                    self.account.available_cash + (executed_amount - commission), 4
                )

                short_position = self._find_position(order.symbol, PositionDirection.SHORT)
                if short_position:
                    total_quantity = short_position.quantity - order.quantity
                    total_cost_value = (
                        abs(short_position.quantity) * short_position.cost_price
                        + order.quantity * executed_price
                    )
                    short_position.cost_price = round(total_cost_value / abs(total_quantity), 4)
                    short_position.quantity = -abs(total_quantity)
                else:
                    new_position = PositionData(
                        symbol=order.symbol,
                        direction=PositionDirection.SHORT,
                        quantity=-order.quantity,  # 负数表示 SHORT
                        available_quantity=-order.quantity,
                        cost_price=executed_price,
                        current_price=executed_price,
                        market_value=-executed_amount,
                        profit_loss=0,
                        profit_loss_rate=0,
                    )
                    self.account.positions.append(new_position)

                order.status = OrderStatus.SUCCESS
                results.append(OrderResultSchema(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    order_type=order.order_type,
                    status=OrderStatus.SUCCESS,
                    timestamp=execution_time,
                    executed_quantity=order.quantity,
                    executed_price=executed_price,
                    executed_amount=executed_amount,
                    commission=commission,
                    message="Opened short position",
                ))

        return results

    # ── 公共 tick 入口 ───────────────────────────

    def pre_tick(self) -> None:
        """每个仿真日的"前置"操作。

        流程:
          1. 读取最新 date / account
          2. 推进订单状态（PENDING -> EXPIRED / 清理超期）
          3. 持久化
        """
        self._load_date_info()
        self.account = self._load_account()
        self._update_order_statuses()
        self._save_account()

    def post_tick(self) -> List[OrderResultSchema]:
        """每个仿真日的"撮合 + 强平"操作。

        流程:
          1. 重新加载最新 date / account
          2. 撮合所有 PENDING 订单
          3. 刷新账户指标
          4. 检查保证金并按需强平
          5. 持久化
          6. 返回撮合 + 强平结果
        """
        self._load_date_info()
        self.account = self._load_account()

        execution_results = self._process_orders()
        self._update_account_metrics()

        # 强平检查（可能在撮合后净值进一步恶化）
        margin_results = self._check_margin_call()
        if margin_results:
            self._update_account_metrics()

        self._save_account()
        return execution_results + margin_results
