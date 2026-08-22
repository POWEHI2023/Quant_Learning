from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from jquant.config import StrategyConfig
from jquant.data.base import MarketData


class SmallCapTechStrategy:
    """Select liquid, seasoned non-ST tech stocks by free-float market cap."""

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def select(self, data: MarketData, signal_date: date) -> list[str]:
        universe = data.industry_stocks(self.config.industry_codes, signal_date)
        universe = [code for code in universe if self._exchange_allowed(code)]
        if not universe:
            return []

        master = data.security_master(universe, signal_date)
        cutoff = signal_date - timedelta(days=self.config.min_listing_days)
        eligible = master[
            master["start_date"].notna()
            & (master["start_date"] <= cutoff)
            & master["end_date"].notna()
            & (master["end_date"] >= signal_date)
        ].index.tolist()
        if not eligible:
            return []

        st = data.st_status(eligible, signal_date)
        eligible = [code for code in eligible if not bool(st.get(code, False))]
        if not eligible:
            return []

        lookback_start = signal_date - timedelta(
            days=max(45, self.config.liquidity_lookback_days * 3)
        )
        bars = data.daily_bars(
            eligible,
            lookback_start,
            signal_date,
            fields=("close", "money", "paused"),
        )
        liquid = self._liquid_codes(bars)
        if not liquid:
            return []

        caps = data.market_caps(liquid, signal_date).dropna(
            subset=["market_cap", "circulating_market_cap"]
        )
        caps = caps[(caps["market_cap"] > 0) & (caps["circulating_market_cap"] > 0)]
        ranked = caps.sort_values(
            ["circulating_market_cap", "market_cap"], kind="stable"
        )
        return ranked.head(self.config.hold_count).index.tolist()

    def _exchange_allowed(self, code: str) -> bool:
        return any(code.endswith(f".{suffix}") for suffix in self.config.allowed_exchange_suffixes)

    def _liquid_codes(self, bars: pd.DataFrame) -> list[str]:
        if bars.empty:
            return []
        ordered = bars.sort_index().groupby(level="code", group_keys=False).tail(
            self.config.liquidity_lookback_days
        )
        grouped = ordered.groupby(level="code")
        observations = grouped["money"].count()
        average_turnover = grouped["money"].mean()
        latest_paused = grouped["paused"].last().fillna(1).astype(bool)
        required = max(1, int(self.config.liquidity_lookback_days * 0.8))
        mask = (
            (observations >= required)
            & (average_turnover >= self.config.min_average_turnover)
            & ~latest_paused
        )
        return mask[mask].index.astype(str).tolist()

