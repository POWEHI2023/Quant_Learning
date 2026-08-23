from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from jquant.config import StrategyConfig
from jquant.strategy.base import FilterContext, StockFilter


class ExchangeFilter(StockFilter):
    name = "exchange"
    description = "只保留配置允许的交易所股票"

    def __init__(self, config: StrategyConfig) -> None:
        self.suffixes = config.allowed_exchange_suffixes

    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        return [
            code for code in codes if any(code.endswith(f".{suffix}") for suffix in self.suffixes)
        ]


class ListingAgeFilter(StockFilter):
    name = "listing_age"
    description = "剔除上市时间不足和信号日已退市的股票"

    def __init__(self, config: StrategyConfig) -> None:
        self.minimum_days = config.min_listing_days

    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        master = context.data.security_master(codes, context.signal_date)
        cutoff = context.signal_date - timedelta(days=self.minimum_days)
        mask = (
            master["start_date"].notna()
            & (master["start_date"] <= cutoff)
            & master["end_date"].notna()
            & (master["end_date"] >= context.signal_date)
        )
        return master[mask].index.astype(str).tolist()


class StFilter(StockFilter):
    name = "st"
    description = "剔除 ST 和 *ST 股票"

    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        status = context.data.st_status(codes, context.signal_date)
        return [code for code in codes if not bool(status.get(code, False))]


class LiquidityFilter(StockFilter):
    name = "liquidity"
    description = "剔除停牌、有效记录不足和平均成交额过低的股票"

    def __init__(self, config: StrategyConfig) -> None:
        self.lookback_days = config.liquidity_lookback_days
        self.minimum_average_turnover = config.min_average_turnover

    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        lookback_start = context.signal_date - timedelta(days=max(45, self.lookback_days * 3))
        bars = context.data.daily_bars(
            codes,
            lookback_start,
            context.signal_date,
            fields=("money", "paused"),
        )
        if bars.empty:
            return []
        ordered = bars.sort_index().groupby(level="code", group_keys=False).tail(
            self.lookback_days
        )
        grouped = ordered.groupby(level="code")
        observations = grouped["money"].count()
        average_turnover = grouped["money"].mean()
        latest_paused = grouped["paused"].last().fillna(1).astype(bool)
        required = max(1, int(self.lookback_days * 0.8))
        mask = (
            (observations >= required)
            & (average_turnover >= self.minimum_average_turnover)
            & ~latest_paused
        )
        eligible = set(mask[mask].index.astype(str))
        return [code for code in codes if code in eligible]


class ProfitabilityFilter(StockFilter):
    name = "profitability"
    description = "按净资产收益率 ROE 过滤盈利能力"
    fundamental_fields = ("roe",)

    def __init__(self, config: StrategyConfig) -> None:
        self.minimum_roe = config.min_roe

    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        values = context.fundamentals(codes)["roe"]
        eligible = set(values[values.notna() & (values >= self.minimum_roe)].index)
        return [code for code in codes if code in eligible]


class DebtRatioFilter(StockFilter):
    name = "debt_ratio"
    description = "按总负债/总资产过滤资产负债率"
    fundamental_fields = ("total_assets", "total_liability")

    def __init__(self, config: StrategyConfig) -> None:
        self.maximum_debt_ratio = config.max_debt_ratio

    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        values = context.fundamentals(codes)
        ratio = values["total_liability"] / values["total_assets"]
        mask = (
            values["total_assets"].notna()
            & values["total_liability"].notna()
            & (values["total_assets"] > 0)
            & ratio.between(0, self.maximum_debt_ratio, inclusive="both")
        )
        eligible = set(values[mask].index)
        return [code for code in codes if code in eligible]


class GrowthFilter(StockFilter):
    name = "growth"
    description = "按营业收入和净利润同比增长率过滤成长性"
    fundamental_fields = ("revenue_growth", "net_profit_growth")

    def __init__(self, config: StrategyConfig) -> None:
        self.minimum_revenue_growth = config.min_revenue_growth
        self.minimum_net_profit_growth = config.min_net_profit_growth

    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        values = context.fundamentals(codes)
        mask = (
            values["revenue_growth"].notna()
            & values["net_profit_growth"].notna()
            & (values["revenue_growth"] >= self.minimum_revenue_growth)
            & (values["net_profit_growth"] >= self.minimum_net_profit_growth)
        )
        eligible = set(values[mask].index)
        return [code for code in codes if code in eligible]


class ValuationFilter(StockFilter):
    name = "valuation"
    description = "按市盈率 PE 和市净率 PB 区间过滤估值"
    fundamental_fields = ("pe_ratio", "pb_ratio")

    def __init__(self, config: StrategyConfig) -> None:
        self.minimum_pe = config.min_pe_ratio
        self.maximum_pe = config.max_pe_ratio
        self.minimum_pb = config.min_pb_ratio
        self.maximum_pb = config.max_pb_ratio

    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        values = context.fundamentals(codes)
        mask = (
            values["pe_ratio"].notna()
            & values["pb_ratio"].notna()
            & values["pe_ratio"].between(self.minimum_pe, self.maximum_pe, inclusive="right")
            & values["pb_ratio"].between(self.minimum_pb, self.maximum_pb, inclusive="right")
        )
        eligible = set(values[mask].index)
        return [code for code in codes if code in eligible]


class MarketCapFilter(StockFilter):
    name = "market_cap"
    description = "剔除总市值或流通市值缺失、非正的股票"
    fundamental_fields = ("market_cap", "circulating_market_cap")

    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]:
        values = context.fundamentals(codes)
        mask = (
            values["market_cap"].notna()
            & values["circulating_market_cap"].notna()
            & (values["market_cap"] > 0)
            & (values["circulating_market_cap"] > 0)
        )
        eligible = set(values[mask].index)
        return [code for code in codes if code in eligible]


def build_default_filters(config: StrategyConfig) -> list[StockFilter]:
    return [
        ExchangeFilter(config),
        ListingAgeFilter(config),
        StFilter(),
        LiquidityFilter(config),
        ProfitabilityFilter(config),
        DebtRatioFilter(config),
        GrowthFilter(config),
        ValuationFilter(config),
        MarketCapFilter(),
    ]

