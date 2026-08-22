from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Protocol

import pandas as pd

from jquant.backtest.costs import TransactionCostModel
from jquant.backtest.metrics import calculate_metrics
from jquant.backtest.models import BacktestResult, Order, Position, RebalancePlan
from jquant.config import AppConfig
from jquant.data.base import MarketData


class Strategy(Protocol):
    def select(self, data: MarketData, signal_date: date) -> list[str]: ...


class BacktestEngine:
    def __init__(self, data: MarketData, strategy: Strategy, config: AppConfig) -> None:
        self.data = data
        self.strategy = strategy
        self.config = config
        self.costs = TransactionCostModel(config.costs)

    def run(self) -> BacktestResult:
        bt = self.config.backtest
        extended_start = bt.start_date - timedelta(days=45)
        all_days = self.data.trade_days(extended_start, bt.end_date)
        trade_days = [day for day in all_days if bt.start_date <= day <= bt.end_date]
        if not trade_days:
            raise ValueError("回测区间内没有交易日")

        plans = self._build_plans(all_days, trade_days)
        securities = sorted({code for plan in plans for code in plan.targets})
        frames: list[pd.DataFrame] = []
        if securities:
            frames.append(
                self.data.daily_bars(
                    securities,
                    trade_days[0],
                    trade_days[-1],
                    fields=("open", "close", "paused", "high_limit", "low_limit"),
                )
            )
        benchmark_bars = self.data.daily_bars(
            [bt.benchmark], trade_days[0], trade_days[-1], fields=("close",)
        )
        for field in ("open", "paused", "high_limit", "low_limit"):
            benchmark_bars[field] = float("nan")
        frames.append(benchmark_bars)
        bars = pd.concat(frames).sort_index()
        if bars.empty:
            raise ValueError("回测行情为空，请检查账号权限和日期范围")
        return self._simulate(trade_days, plans, bars)

    def _build_plans(
        self, all_days: list[date], trade_days: list[date]
    ) -> list[RebalancePlan]:
        all_index = {day: index for index, day in enumerate(all_days)}
        execution_days = [
            day
            for index, day in enumerate(trade_days)
            if index == 0 or (day.year, day.month) != (
                trade_days[index - 1].year,
                trade_days[index - 1].month,
            )
        ]
        plans: list[RebalancePlan] = []
        for execution_day in execution_days:
            index = all_index[execution_day]
            if index == 0:
                continue
            signal_day = all_days[index - 1]
            targets = tuple(self.strategy.select(self.data, signal_day))
            plans.append(RebalancePlan(signal_day, execution_day, targets))
        return plans

    def _simulate(
        self,
        trade_days: list[date],
        plans: list[RebalancePlan],
        bars: pd.DataFrame,
    ) -> BacktestResult:
        bt = self.config.backtest
        cash = bt.initial_cash
        positions: dict[str, Position] = {}
        orders: list[Order] = []
        last_close: dict[str, float] = {}
        plan_by_day = {plan.execution_date: plan for plan in plans}
        rows: list[dict[str, float | pd.Timestamp]] = []

        for day in trade_days:
            timestamp = pd.Timestamp(day)
            if day in plan_by_day:
                cash, positions, day_orders = self._rebalance(
                    day,
                    plan_by_day[day].targets,
                    cash,
                    positions,
                    bars,
                    last_close,
                )
                orders.extend(day_orders)

            market_value = 0.0
            for code, position in positions.items():
                close = self._price(bars, timestamp, code, "close")
                if close is not None:
                    last_close[code] = close
                mark = last_close.get(code, position.average_cost)
                market_value += position.shares * mark

            benchmark = self._price(bars, timestamp, bt.benchmark, "close")
            rows.append(
                {
                    "date": timestamp,
                    "equity": cash + market_value,
                    "cash": cash,
                    "market_value": market_value,
                    "benchmark": benchmark,
                }
            )

        curve = pd.DataFrame(rows).set_index("date")
        curve["daily_return"] = curve["equity"].pct_change().fillna(0.0)
        result = BacktestResult(equity_curve=curve, orders=orders, plans=plans)
        result.metrics = calculate_metrics(
            curve, self.config.metrics, initial_equity=self.config.backtest.initial_cash
        )
        return result

    def _rebalance(
        self,
        day: date,
        targets: tuple[str, ...],
        cash: float,
        positions: dict[str, Position],
        bars: pd.DataFrame,
        last_close: dict[str, float],
    ) -> tuple[float, dict[str, Position], list[Order]]:
        timestamp = pd.Timestamp(day)
        codes = set(targets) | set(positions)
        open_prices: dict[str, float] = {}
        for code in codes:
            price = self._price(bars, timestamp, code, "open")
            if price is not None:
                open_prices[code] = price

        equity_at_open = cash + sum(
            position.shares
            * open_prices.get(code, last_close.get(code, position.average_cost))
            for code, position in positions.items()
        )
        target_value = (
            equity_at_open * (1 - self.config.strategy.cash_buffer) / len(targets)
            if targets
            else 0.0
        )
        desired: dict[str, int] = {}
        lot = self.config.costs.lot_size
        for code in targets:
            price = open_prices.get(code)
            desired[code] = math.floor(target_value / price / lot) * lot if price else 0

        orders: list[Order] = []
        for code in sorted(positions):
            current = positions[code].shares
            shares = current - desired.get(code, 0)
            if shares <= 0:
                continue
            order = self._sell(day, code, shares, positions, bars, timestamp)
            orders.append(order)
            if order.status == "filled":
                cash += order.notional - order.fees

        for code in targets:
            current = positions.get(code, Position(code, 0, 0.0)).shares
            shares = desired.get(code, 0) - current
            if shares <= 0:
                continue
            order = self._buy(day, code, shares, cash, positions, bars, timestamp)
            orders.append(order)
            if order.status == "filled":
                cash -= order.notional + order.fees

        positions = {code: position for code, position in positions.items() if position.shares > 0}
        return cash, positions, orders

    def _sell(
        self,
        day: date,
        code: str,
        shares: int,
        positions: dict[str, Position],
        bars: pd.DataFrame,
        timestamp: pd.Timestamp,
    ) -> Order:
        reference = self._price(bars, timestamp, code, "open")
        reason = self._untradable_reason(bars, timestamp, code, "sell", reference)
        if reason:
            return Order(day, code, "sell", shares, 0.0, 0.0, 0.0, "rejected", reason)
        assert reference is not None
        price = self.costs.execution_price(reference, "sell")
        notional = shares * price
        fees = self.costs.fees(notional, "sell")
        positions[code].shares -= shares
        return Order(day, code, "sell", shares, price, notional, fees)

    def _buy(
        self,
        day: date,
        code: str,
        desired_shares: int,
        cash: float,
        positions: dict[str, Position],
        bars: pd.DataFrame,
        timestamp: pd.Timestamp,
    ) -> Order:
        reference = self._price(bars, timestamp, code, "open")
        reason = self._untradable_reason(bars, timestamp, code, "buy", reference)
        if reason:
            return Order(day, code, "buy", desired_shares, 0.0, 0.0, 0.0, "rejected", reason)
        assert reference is not None
        price = self.costs.execution_price(reference, "buy")
        shares = self.costs.affordable_shares(cash, price, desired_shares)
        if shares <= 0:
            return Order(
                day, code, "buy", desired_shares, price, 0.0, 0.0, "rejected", "现金不足"
            )
        notional = shares * price
        fees = self.costs.fees(notional, "buy")
        current = positions.get(code)
        if current:
            total_cost = current.average_cost * current.shares + notional + fees
            current.shares += shares
            current.average_cost = total_cost / current.shares
        else:
            positions[code] = Position(code, shares, (notional + fees) / shares)
        return Order(day, code, "buy", shares, price, notional, fees)

    @staticmethod
    def _price(
        bars: pd.DataFrame, timestamp: pd.Timestamp, code: str, field: str
    ) -> float | None:
        try:
            value = bars.loc[(timestamp, code), field]
        except KeyError:
            return None
        if isinstance(value, pd.Series):
            value = value.iloc[-1]
        return float(value) if pd.notna(value) and float(value) > 0 else None

    def _untradable_reason(
        self,
        bars: pd.DataFrame,
        timestamp: pd.Timestamp,
        code: str,
        side: str,
        open_price: float | None,
    ) -> str:
        if open_price is None:
            return "缺少开盘价"
        paused = self._value(bars, timestamp, code, "paused")
        if paused is None or bool(paused):
            return "停牌或无交易状态"
        limit_field = "high_limit" if side == "buy" else "low_limit"
        limit_price = self._price(bars, timestamp, code, limit_field)
        if limit_price is not None:
            if side == "buy" and open_price >= limit_price - 1e-8:
                return "开盘涨停"
            if side == "sell" and open_price <= limit_price + 1e-8:
                return "开盘跌停"
        return ""

    @staticmethod
    def _value(
        bars: pd.DataFrame, timestamp: pd.Timestamp, code: str, field: str
    ) -> float | None:
        try:
            value = bars.loc[(timestamp, code), field]
        except KeyError:
            return None
        if isinstance(value, pd.Series):
            value = value.iloc[-1]
        return float(value) if pd.notna(value) else None
