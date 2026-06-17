"""
A 股仿真撮合引擎（Exchange）

功能概述：
    在 A 股市场规则下对策略订单进行撮合、结算、账户更新。
    对外暴露 pre_tick / post_tick 两个钩子，分别在策略运行前/后调用。

A 股关键规则：
    - T+1 结算：当日买入的股票次日才可卖出
    - 数量为 100 的整数倍（一手）
    - 不允许做空：SELL 仅用于减仓/平 LONG
    - 撮合时间：每个交易日 14:30（仿真时钟统一为该时刻）
    - 撮合价：当日 close 价（前提：订单价格在当日 low~high 区间内）
    - 订单时效：PENDING > 7 个交易日自动 EXPIRED；> 14 个交易日被移除
    - 手续费率：0.02%

数据流（每日循环）：
    ┌─────────────┐  pre_tick   ┌─────────────┐
    │ 读取 date  │ ──────────→ │ T+1 解锁可用量 │
    │ 加载 account│            │ 清理过期订单   │
    └──────┬──────┘            │ 更新账户指标   │
           ▼                   └──────┬──────┘
    ┌─────────────┐                    │
    │ Hook.on_tick│ (策略生成新订单)     │
    └──────┬──────┘                    │
           ▼                           │
    ┌─────────────┐  post_tick         │
    │ 撮合 PENDING │ ←─────────────────┘
    │ 更新账户     │
    │ 持久化到 JSON│
    └─────────────┘
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
    """A 股仿真撮合引擎。"""

    def __init__(self, dataset_dir_path: str, account_file_path: str, date_file_path: str):
        """初始化 A 股 Exchange。

        参数:
            dataset_dir_path: 股票 CSV 文件所在目录。
            account_file_path: 账户 JSON 文件路径（用于持久化）。
            date_file_path:    date.json 路径（含 current_date 与 trading_days）。

        异常:
            FileNotFoundError: 账户文件或 date.json 不存在。
        """
        self.dataset_dir_path = Path(dataset_dir_path)
        self.account_file_path = Path(account_file_path)
        self.date_file_path = Path(date_file_path)

        # ── 必要文件存在性检查 ──
        if not self.account_file_path.exists():
            raise FileNotFoundError(f"Account file not found: {account_file_path}")
        if not self.date_file_path.exists():
            raise FileNotFoundError(f"Date file not found: {date_file_path}")

        self.market_data: Dict[str, pd.DataFrame] = {}
        self.account: AccountSchema = None  # 每次 pre/post_tick 时重新加载

        # A 股手续费率
        self.commission_rate = 0.0002  # 0.02%

        # 一次性加载全市场行情到内存
        self._load_market_data()

    # ── 日期 / 行情 加载 ───────────────────────────

    def _load_date_info(self) -> None:
        """从 date.json 读取当前日期与交易日序列。

        业务约定：仿真时钟统一指向 14:30 收盘前撮合时点。
        """
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
        """在 trading_days 列表中取前一个交易日。"""
        try:
            current_idx = self.trading_days.index(self.current_date_str)
            if current_idx > 0:
                return self.trading_days[current_idx - 1]
            return None
        except ValueError:
            return None

    def _load_market_data(self) -> None:
        """将 dataset 目录下的所有 CSV 加载到内存字典（symbol -> DataFrame）。"""
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
        """从 JSON 加载账户，反序列化为 Pydantic 对象。"""
        try:
            with open(self.account_file_path, 'r') as f:
                data = json.load(f)

            positions = []
            for pos_data in data.get('positions', []):
                # 老数据可能没有 direction 字段，向前兼容默认 LONG
                if 'direction' not in pos_data:
                    pos_data['direction'] = PositionDirection.LONG
                positions.append(PositionData(**pos_data))

            orders = []
            for order_data in data.get('orders', []):
                # timestamp 字段在 JSON 中是字符串，需转回 datetime
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
        """将账户对象写回 JSON，自动做数值精度与类型转换。"""
        account_dict = self.account.model_dump()

        # 比例字段保留 4 位小数
        for field in ['total_profit_loss_rate', 'gross_position_rate', 'net_position_rate']:
            if field in account_dict:
                account_dict[field] = round(account_dict[field], 4)

        # 资金类字段保留 4 位小数
        for field in ['total_assets', 'net_assets', 'available_cash', 'market_value', 'total_profit_loss']:
            if field in account_dict:
                account_dict[field] = round(account_dict[field], 4)

        # 持仓字段精度处理
        for position in account_dict.get('positions', []):
            for field in ['cost_price', 'current_price', 'market_value', 'profit_loss', 'profit_loss_rate']:
                if field in position:
                    position[field] = round(position[field], 4)
            # 枚举 -> 字符串，便于 JSON 序列化
            if 'direction' in position and hasattr(position['direction'], 'value'):
                position['direction'] = position['direction'].value

        # 订单字段精度与时间格式
        for order in account_dict.get('orders', []):
            if 'price' in order:
                order['price'] = round(order['price'], 4)
            if isinstance(order.get('timestamp'), datetime):
                order['timestamp'] = order['timestamp'].isoformat()

        # 持久化
        self.account_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.account_file_path, 'w') as f:
            json.dump(account_dict, f, indent=2, default=str)

    # ── 行情查询 ───────────────────────────

    def _get_price_data(self, symbol: str, date: datetime) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """取某 symbol 在某日期的 (low, high, close)。

        若当日无数据则回退到最近历史日（停牌/退市场景）。
        """
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

    def _find_position(self, symbol: str, direction: PositionDirection = PositionDirection.LONG) -> Optional[PositionData]:
        """根据 symbol + direction 查找持仓。"""
        for position in self.account.positions:
            if position.symbol == symbol and position.direction == direction:
                return position
        return None

    def _remove_position(self, symbol: str, direction: PositionDirection = PositionDirection.LONG) -> None:
        """从账户持仓列表中移除指定 (symbol, direction) 的持仓。"""
        self.account.positions = [
            p for p in self.account.positions
            if not (p.symbol == symbol and p.direction == direction)
        ]

    # ── 订单生命周期 ───────────────────────────

    def _update_order_statuses(self) -> None:
        """按订单"年龄"推进状态：
            - PENDING > 7 个交易日 -> EXPIRED
            - 任何订单 > 14 个交易日 -> 物理删除
        """
        updated_orders = []

        for order in self.account.orders:
            try:
                # 用交易日序号计算"过了多少个交易日"
                order_idx = self.trading_days.index(order.timestamp.strftime('%Y-%m-%d'))
                current_idx = self.trading_days.index(self.current_date_str)
                days_diff = current_idx - order_idx
            except ValueError:
                # 极端情况下用日历日兜底
                days_diff = (self.current_date - order.timestamp).days

            if days_diff > 14:
                # 超过 14 个交易日的订单直接清除
                continue

            if order.status == OrderStatus.PENDING and days_diff > 7:
                # PENDING 超期 -> EXPIRED（保留用于审计）
                order.status = OrderStatus.EXPIRED
                updated_orders.append(order)
            else:
                updated_orders.append(order)

        self.account.orders = updated_orders

    # ── 账户指标更新 ───────────────────────────

    def _update_account_metrics(self) -> None:
        """用最新价格刷新每个持仓的 current_price / P&L / market_value，并汇总账户指标。"""
        total_market_value = 0
        total_long_market_value = 0
        total_short_market_value = 0

        for position in self.account.positions:
            _, _, current_price = self._get_price_data(position.symbol, self.current_date)

            if current_price is not None:
                position.current_price = current_price
                position.market_value = position.quantity * current_price

                # LONG: 赚 = (现价 - 成本) * 数量
                if position.direction == PositionDirection.LONG:
                    position.profit_loss = (current_price - position.cost_price) * position.quantity
                else:  # SHORT（仅在 schema 层面保留，A 股不会进入此分支）
                    position.profit_loss = (position.cost_price - current_price) * position.quantity

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
                # 停牌：保持上一次快照的市值
                total_market_value += position.market_value
                if position.direction == PositionDirection.LONG:
                    total_long_market_value += position.market_value
                else:
                    total_short_market_value += position.market_value

        # ── 汇总账户层指标 ──
        self.account.market_value = round(total_market_value, 4)
        self.account.net_assets = round(self.account.available_cash + total_market_value, 4)
        self.account.total_assets = self.account.net_assets

        initial_capital = 10_000_000  # A 股初始资金 1000 万 CNY
        self.account.total_profit_loss = round(self.account.total_assets - initial_capital, 4)
        if initial_capital > 0:
            self.account.total_profit_loss_rate = round(
                (self.account.total_assets - initial_capital) / initial_capital, 4
            )
        else:
            self.account.total_profit_loss_rate = 0

        # 总仓位 = 绝对敞口 / 净值
        gross_exposure = sum(abs(p.market_value) for p in self.account.positions)
        self.account.gross_position_rate = (
            round(gross_exposure / self.account.net_assets, 4)
            if self.account.net_assets > 0 else 0
        )

        # 净仓位 = (long - short) / 净值（A 股下 short_market_value = 0）
        net_market_value = total_long_market_value - total_short_market_value
        self.account.net_position_rate = (
            round(net_market_value / self.account.net_assets, 4)
            if self.account.net_assets > 0 else 0
        )

    # ── 订单撮合 ───────────────────────────

    def _process_orders(self) -> List[OrderResultSchema]:
        """对所有 PENDING 订单尝试撮合；返回本次撮合/失败结果。

        撮合规则：
          - 订单价格必须在当日 low ~ high 区间内，否则保持 PENDING
          - 撮合价统一使用 close
          - 资金不足 / 可用持仓不足 -> FAILED
        """
        results = []
        execution_time = self.current_date

        # 复制订单列表避免迭代中修改
        orders_to_process = list(self.account.orders)

        for order in orders_to_process:
            if order.status != OrderStatus.PENDING:
                continue

            low, high, close = self._get_price_data(order.symbol, self.current_date)
            if low is None or high is None:
                # 无行情（停牌/未上市），保持 PENDING 等下一日
                print(f"Order {order.order_id}: Cannot execute - no market data for {order.symbol} (possibly suspended)")
                continue

            if not (low <= order.price <= high):
                # 价格不在当日区间内 -> 当日不成交
                continue

            # ── 进入撮合 ──
            executed_price = close
            executed_amount = executed_price * order.quantity
            commission = round(executed_amount * self.commission_rate, 4)
            executed_amount = round(executed_amount, 4)

            if order.order_type == OrderType.BUY:
                # 买入：扣减现金 + 增加持仓
                total_cost = executed_amount + commission
                if self.account.available_cash >= total_cost:
                    self.account.available_cash = round(self.account.available_cash - total_cost, 4)

                    position = self._find_position(order.symbol, PositionDirection.LONG)
                    if position:
                        # 加仓：成本价做加权平均
                        total_quantity = position.quantity + order.quantity
                        total_cost_value = (
                            position.quantity * position.cost_price
                            + order.quantity * executed_price
                        )
                        position.cost_price = round(total_cost_value / total_quantity, 4)
                        position.quantity = total_quantity
                        # T+1：available_quantity 保持不变（今日买入不可卖）
                    else:
                        # 建仓：可用量先为 0（T+1）
                        new_position = PositionData(
                            symbol=order.symbol,
                            direction=PositionDirection.LONG,
                            quantity=order.quantity,
                            available_quantity=0,
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
                # 卖出：仅支持减少 LONG（A 股不允许做空）
                position = self._find_position(order.symbol, PositionDirection.LONG)
                if position and position.available_quantity >= order.quantity:
                    # 加现金：成交额 - 手续费
                    self.account.available_cash = round(
                        self.account.available_cash + (executed_amount - commission), 4
                    )
                    position.quantity -= order.quantity
                    position.available_quantity -= order.quantity

                    if position.quantity <= 0:
                        self._remove_position(order.symbol, PositionDirection.LONG)

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
                    extra_msg = ""
                    if position and position.available_quantity < order.quantity:
                        extra_msg = " (T+1: shares not available yet)"
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
                        message="Insufficient shares" + extra_msg,
                    ))

        return results

    # ── T+1 解锁 ───────────────────────────

    def _update_available_quantities(self) -> None:
        """T+1 解锁：昨日成交的 BUY 数量今日加入 available_quantity。"""
        prev_trading_day = self._get_previous_trading_day()
        if not prev_trading_day:
            return

        for order in self.account.orders:
            if order.status == OrderStatus.SUCCESS and order.order_type == OrderType.BUY:
                if order.timestamp.strftime('%Y-%m-%d') == prev_trading_day:
                    # 昨日买入今日才可卖
                    position = self._find_position(order.symbol, PositionDirection.LONG)
                    if position:
                        position.available_quantity += order.quantity

    # ── 公共 tick 入口 ───────────────────────────

    def pre_tick(self) -> None:
        """每个仿真日的"前置"操作。

        流程:
          1. 读取最新 date / account
          2. T+1 解锁可用量
          3. 推进订单状态（PENDING -> EXPIRED / 清理超期）
          4. 刷新账户指标
          5. 持久化
        """
        self._load_date_info()
        self.account = self._load_account()

        self._update_available_quantities()
        self._update_order_statuses()
        self._update_account_metrics()
        self._save_account()

    def post_tick(self) -> List[OrderResultSchema]:
        """每个仿真日的"撮合"操作（在策略生成订单后调用）。

        流程:
          1. 重新加载最新 date / account
          2. 撮合所有 PENDING 订单
          3. 刷新账户指标
          4. 持久化
          5. 返回本次撮合结果列表
        """
        self._load_date_info()
        self.account = self._load_account()

        execution_results = self._process_orders()
        self._update_account_metrics()
        self._save_account()

        return execution_results
