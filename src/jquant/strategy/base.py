from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from jquant.data.base import MarketData


class StockFilter(ABC):
    """One independently configurable stock-universe condition."""

    name: str
    description: str
    fundamental_fields: tuple[str, ...] = ()

    @abstractmethod
    def apply(self, codes: Sequence[str], context: FilterContext) -> list[str]: ...


class FilterRegistry:
    def __init__(self, filters: Iterable[StockFilter] = ()) -> None:
        self._filters: dict[str, StockFilter] = {}
        for stock_filter in filters:
            self.register(stock_filter)

    def register(self, stock_filter: StockFilter) -> None:
        if stock_filter.name in self._filters:
            raise ValueError(f"过滤器已注册: {stock_filter.name}")
        self._filters[stock_filter.name] = stock_filter

    def get(self, name: str) -> StockFilter:
        try:
            return self._filters[name]
        except KeyError as exc:
            raise ValueError(f"未注册的过滤器: {name}") from exc

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._filters)

    def values(self) -> tuple[StockFilter, ...]:
        return tuple(self._filters.values())


@dataclass
class FilterContext:
    data: MarketData
    signal_date: date
    required_fundamental_fields: tuple[str, ...]
    _fundamentals: pd.DataFrame | None = field(default=None, init=False, repr=False)

    def fundamentals(self, codes: Sequence[str]) -> pd.DataFrame:
        if self._fundamentals is None:
            self._fundamentals = self.data.fundamentals(
                list(codes), self.signal_date, self.required_fundamental_fields
            )
        return self._fundamentals.reindex(list(codes))


class BaseStrategy(ABC):
    """Common filter registration, selection pipeline and introspection."""

    ranking_fundamental_fields: tuple[str, ...] = ()

    def __init__(
        self,
        filters: Iterable[StockFilter],
        enabled_filters: Sequence[str],
    ) -> None:
        self._filter_registry = FilterRegistry(filters)
        self._enabled_filters: tuple[str, ...] = ()
        self.set_enabled_filters(enabled_filters)

    @property
    def registered_filters(self) -> tuple[str, ...]:
        return self._filter_registry.names

    @property
    def enabled_filters(self) -> tuple[str, ...]:
        return self._enabled_filters

    def filter_status(self) -> list[dict[str, str | bool]]:
        enabled = set(self.enabled_filters)
        return [
            {
                "name": stock_filter.name,
                "description": stock_filter.description,
                "enabled": stock_filter.name in enabled,
            }
            for stock_filter in self._filter_registry.values()
        ]

    def set_enabled_filters(self, names: Sequence[str]) -> None:
        selected = tuple(names)
        if len(selected) != len(set(selected)):
            raise ValueError("启用的过滤器列表不能包含重复项")
        unknown = set(selected) - set(self.registered_filters)
        if unknown:
            raise ValueError(f"策略包含未注册的过滤器: {sorted(unknown)}")
        self._enabled_filters = selected

    def select(self, data: MarketData, signal_date: date) -> list[str]:
        candidates = self.build_universe(data, signal_date)
        if not candidates:
            return []

        required_fields = set(self.ranking_fundamental_fields)
        for name in self.enabled_filters:
            required_fields.update(self._filter_registry.get(name).fundamental_fields)
        context = FilterContext(data, signal_date, tuple(sorted(required_fields)))

        for name in self.enabled_filters:
            candidates = self._filter_registry.get(name).apply(candidates, context)
            if not candidates:
                return []
        return self.rank(candidates, context)

    @abstractmethod
    def build_universe(self, data: MarketData, signal_date: date) -> list[str]: ...

    @abstractmethod
    def rank(self, codes: Sequence[str], context: FilterContext) -> list[str]: ...

