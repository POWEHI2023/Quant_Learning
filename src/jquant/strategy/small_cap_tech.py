from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from jquant.config import StrategyConfig
from jquant.data.base import MarketData
from jquant.strategy.base import BaseStrategy, FilterContext
from jquant.strategy.filters import build_default_filters


class SmallCapTechStrategy(BaseStrategy):
    """Select liquid, seasoned non-ST tech stocks by free-float market cap."""

    ranking_fundamental_fields = ("market_cap", "circulating_market_cap")

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        super().__init__(build_default_filters(config), config.enabled_filters)

    def build_universe(self, data: MarketData, signal_date: date) -> list[str]:
        return data.industry_stocks(self.config.industry_codes, signal_date)

    def rank(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        caps = context.fundamentals(codes).dropna(
            subset=["market_cap", "circulating_market_cap"]
        )
        ranked = caps.sort_values(
            ["circulating_market_cap", "market_cap"], kind="stable"
        )
        return ranked.head(self.config.hold_count).index.tolist()
