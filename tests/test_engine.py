from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd

from jquant.backtest.engine import BacktestEngine
from jquant.config import (
    AppConfig,
    BacktestConfig,
    CostConfig,
    MetricsConfig,
    StrategyConfig,
)


class FixedStrategy:
    def select(self, data: object, signal_date: date) -> list[str]:
        return ["000001.XSHE"]


class EngineData:
    def __init__(self) -> None:
        self.days = [day.date() for day in pd.bdate_range("2025-01-30", "2025-02-07")]

    def trade_days(self, start: date, end: date) -> list[date]:
        return [day for day in self.days if start <= day <= end]

    def daily_bars(
        self,
        codes: Sequence[str],
        start: date,
        end: date,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        days = [pd.Timestamp(day) for day in self.days if start <= day <= end]
        index = pd.MultiIndex.from_product([days, codes], names=["date", "code"])
        frame = pd.DataFrame(index=index, columns=fields, dtype=float)
        defaults = {
            "open": 10.0,
            "close": 11.0,
            "paused": 0,
            "high_limit": 12.0,
            "low_limit": 8.0,
        }
        for field, value in defaults.items():
            if field in frame:
                frame[field] = value
        if "000300.XSHG" in codes:
            benchmark_rows = frame.index.get_level_values("code") == "000300.XSHG"
            frame.loc[benchmark_rows, "close"] = 101
        return frame


def make_config() -> AppConfig:
    return AppConfig(
        backtest=BacktestConfig(
            start_date=date(2025, 2, 3),
            end_date=date(2025, 2, 7),
            initial_cash=100_000,
        ),
        strategy=StrategyConfig(cash_buffer=0.02),
        costs=CostConfig(slippage_bps=0, transfer_fee_rate=0),
        metrics=MetricsConfig(),
    )


def test_engine_signals_previous_day_and_buys_at_open() -> None:
    result = BacktestEngine(EngineData(), FixedStrategy(), make_config()).run()

    assert result.plans[0].signal_date == date(2025, 1, 31)
    assert result.plans[0].execution_date == date(2025, 2, 3)
    filled = [order for order in result.orders if order.status == "filled"]
    assert len(filled) == 1
    assert filled[0].side == "buy"
    assert filled[0].price == 10.0
    assert filled[0].shares % 100 == 0
    assert result.equity_curve.iloc[-1]["equity"] > 100_000


def test_engine_rejects_open_limit_up_buy() -> None:
    data = EngineData()
    original = data.daily_bars

    def limit_up_bars(
        codes: Sequence[str], start: date, end: date, fields: Sequence[str]
    ) -> pd.DataFrame:
        frame = original(codes, start, end, fields)
        if "000001.XSHE" in codes and "high_limit" in frame:
            key = (pd.Timestamp("2025-02-03"), "000001.XSHE")
            frame.loc[key, "high_limit"] = 10.0
        return frame

    data.daily_bars = limit_up_bars  # type: ignore[method-assign]
    result = BacktestEngine(data, FixedStrategy(), make_config()).run()

    assert result.orders[0].status == "rejected"
    assert result.orders[0].reason == "开盘涨停"
