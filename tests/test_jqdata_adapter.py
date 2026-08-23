from datetime import date

import jqdatasdk as jq
import pandas as pd
import pytest

from jquant.data.jqdata import JQDataSource, _normalize_price_frame


def test_normalize_multi_security_price_frame() -> None:
    raw = pd.DataFrame(
        {
            "time": [pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-02")],
            "code": ["000001.XSHE", "600000.XSHG"],
            "open": [10.0, 20.0],
            "close": [10.5, 20.5],
        }
    )

    normalized = _normalize_price_frame(
        raw, ["000001.XSHE", "600000.XSHG"], ["open", "close"]
    )

    assert normalized.index.names == ["date", "code"]
    assert normalized.loc[(pd.Timestamp("2025-01-02"), "600000.XSHG"), "close"] == 20.5


def test_normalize_single_security_indexed_price_frame() -> None:
    raw = pd.DataFrame(
        {"open": [10.0], "close": [10.5]},
        index=pd.DatetimeIndex(["2025-01-02"]),
    )

    normalized = _normalize_price_frame(raw, ["000001.XSHE"], ["open", "close"])

    assert normalized.index[0] == (pd.Timestamp("2025-01-02"), "000001.XSHE")


class FakeFundamentalSdk:
    valuation = jq.valuation
    indicator = jq.indicator
    balance = jq.balance
    query = staticmethod(jq.query)

    def get_fundamentals(self, query: object, date: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "code": ["000001.XSHE"],
                "roe": [10.0],
                "inc_revenue_year_on_year": [8.0],
                "total_assets": [100.0],
                "total_liability": [40.0],
                "pe_ratio": [30.0],
            }
        )


def make_fundamental_source() -> JQDataSource:
    source = object.__new__(JQDataSource)
    source._jq = FakeFundamentalSdk()
    return source


def test_fundamentals_maps_sdk_columns_to_strategy_fields() -> None:
    source = make_fundamental_source()

    frame = source.fundamentals(
        ["000001.XSHE"],
        date(2025, 1, 31),
        ["roe", "revenue_growth", "total_assets", "total_liability", "pe_ratio"],
    )

    assert frame.loc["000001.XSHE", "revenue_growth"] == 8.0
    assert frame.loc["000001.XSHE", "total_liability"] == 40.0


def test_fundamentals_rejects_unknown_field() -> None:
    source = make_fundamental_source()

    with pytest.raises(ValueError, match="不支持"):
        source.fundamentals(["000001.XSHE"], date(2025, 1, 31), ["mystery"])
