import pandas as pd

from jquant.data.jqdata import _normalize_price_frame


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
