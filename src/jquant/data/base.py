from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

import pandas as pd


class MarketData(Protocol):
    """Data boundary used by strategy and backtest code."""

    def trade_days(self, start: date, end: date) -> list[date]: ...

    def industry_stocks(self, industry_codes: Sequence[str], as_of: date) -> list[str]: ...

    def security_master(self, codes: Sequence[str], as_of: date) -> pd.DataFrame: ...

    def st_status(self, codes: Sequence[str], as_of: date) -> pd.Series: ...

    def market_caps(self, codes: Sequence[str], as_of: date) -> pd.DataFrame: ...

    def daily_bars(
        self,
        codes: Sequence[str],
        start: date,
        end: date,
        fields: Sequence[str],
    ) -> pd.DataFrame: ...
