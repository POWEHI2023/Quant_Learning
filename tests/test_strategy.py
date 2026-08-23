from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

import pandas as pd
import pytest

from jquant.config import StrategyConfig
from jquant.strategy.small_cap_tech import SmallCapTechStrategy


class StrategyData:
    codes = ["000001.XSHE", "000002.XSHE", "000003.XSHE", "430001.XBEI"]

    def industry_stocks(self, industry_codes: Sequence[str], as_of: date) -> list[str]:
        return self.codes

    def security_master(self, codes: Sequence[str], as_of: date) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "start_date": [as_of - timedelta(days=500)] * len(codes),
                "end_date": [as_of + timedelta(days=500)] * len(codes),
            },
            index=codes,
        )

    def st_status(self, codes: Sequence[str], as_of: date) -> pd.Series:
        return pd.Series({code: code == "000003.XSHE" for code in codes})

    def fundamentals(
        self,
        codes: Sequence[str],
        as_of: date,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "market_cap": [30.0, 20.0, 8.0, 5.0],
                "circulating_market_cap": [10.0, 15.0, 4.0, 3.0],
                "roe": [10.0, 8.0, 9.0, 12.0],
                "total_assets": [100.0, 100.0, 100.0, 100.0],
                "total_liability": [40.0, 50.0, 30.0, 20.0],
                "revenue_growth": [10.0, 5.0, 8.0, 6.0],
                "net_profit_growth": [8.0, 4.0, 7.0, 5.0],
                "pe_ratio": [30.0, 40.0, 20.0, 25.0],
                "pb_ratio": [3.0, 4.0, 2.0, 2.5],
            },
            index=self.codes,
        )
        return frame.reindex(codes)[list(fields)]

    def daily_bars(
        self,
        codes: Sequence[str],
        start: date,
        end: date,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        days = pd.bdate_range(end=pd.Timestamp(end), periods=20)
        index = pd.MultiIndex.from_product([days, codes], names=["date", "code"])
        return pd.DataFrame({"money": 20_000_000.0, "paused": 0}, index=index)


def test_strategy_filters_exchange_and_st_then_ranks_free_float_cap() -> None:
    strategy = SmallCapTechStrategy(
        StrategyConfig(hold_count=2, liquidity_lookback_days=20)
    )

    selected = strategy.select(StrategyData(), date(2025, 1, 31))

    assert selected == ["000001.XSHE", "000002.XSHE"]


def test_strategy_exposes_registered_and_enabled_filters() -> None:
    strategy = SmallCapTechStrategy(StrategyConfig())

    assert strategy.registered_filters == (
        "exchange",
        "listing_age",
        "st",
        "liquidity",
        "profitability",
        "debt_ratio",
        "growth",
        "valuation",
        "market_cap",
    )
    assert all(item["enabled"] for item in strategy.filter_status())


def test_strategy_can_change_enabled_filter_list() -> None:
    strategy = SmallCapTechStrategy(StrategyConfig(hold_count=4))
    strategy.set_enabled_filters(["exchange", "market_cap"])

    selected = strategy.select(StrategyData(), date(2025, 1, 31))

    assert strategy.enabled_filters == ("exchange", "market_cap")
    assert selected == ["000003.XSHE", "000001.XSHE", "000002.XSHE"]


class FinancialFilterData(StrategyData):
    codes = [
        "000001.XSHE",
        "000002.XSHE",
        "000003.XSHE",
        "000004.XSHE",
        "000005.XSHE",
        "000006.XSHE",
    ]

    def st_status(self, codes: Sequence[str], as_of: date) -> pd.Series:
        return pd.Series(False, index=codes)

    def fundamentals(
        self,
        codes: Sequence[str],
        as_of: date,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "market_cap": [20.0] * 6,
                "circulating_market_cap": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
                "roe": [10.0, 4.0, 10.0, 10.0, 10.0, 10.0],
                "total_assets": [100.0] * 6,
                "total_liability": [40.0, 40.0, 80.0, 40.0, 40.0, 40.0],
                "revenue_growth": [10.0, 10.0, 10.0, -1.0, 10.0, 10.0],
                "net_profit_growth": [10.0, 10.0, 10.0, 10.0, -1.0, 10.0],
                "pe_ratio": [30.0, 30.0, 30.0, 30.0, 30.0, 120.0],
                "pb_ratio": [3.0] * 6,
            },
            index=self.codes,
        )
        return frame.reindex(codes)[list(fields)]


def test_all_enabled_financial_filters_are_applied_in_select() -> None:
    strategy = SmallCapTechStrategy(StrategyConfig(hold_count=10))

    selected = strategy.select(FinancialFilterData(), date(2025, 1, 31))

    assert selected == ["000001.XSHE"]


def test_strategy_rejects_unregistered_filter() -> None:
    strategy = SmallCapTechStrategy(StrategyConfig())

    with pytest.raises(ValueError, match="未注册"):
        strategy.set_enabled_filters(["not_a_filter"])
