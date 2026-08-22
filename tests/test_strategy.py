from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

import pandas as pd

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

    def market_caps(self, codes: Sequence[str], as_of: date) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "market_cap": [30.0, 20.0],
                "circulating_market_cap": [10.0, 15.0],
            },
            index=["000001.XSHE", "000002.XSHE"],
        )

    def daily_bars(
        self,
        codes: Sequence[str],
        start: date,
        end: date,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        days = pd.bdate_range(end=pd.Timestamp(end), periods=20)
        index = pd.MultiIndex.from_product([days, codes], names=["date", "code"])
        return pd.DataFrame({"close": 10.0, "money": 20_000_000.0, "paused": 0}, index=index)


def test_strategy_filters_exchange_and_st_then_ranks_free_float_cap() -> None:
    strategy = SmallCapTechStrategy(
        StrategyConfig(hold_count=2, liquidity_lookback_days=20)
    )

    selected = strategy.select(StrategyData(), date(2025, 1, 31))

    assert selected == ["000001.XSHE", "000002.XSHE"]
