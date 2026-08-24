import json
from datetime import date

import pandas as pd

from jquant.data.local import ParquetDataSource


def test_parquet_source_reads_snapshot_and_bars(tmp_path) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": 1}))
    meta = tmp_path / "meta"
    meta.mkdir()
    pd.DataFrame({"date": pd.to_datetime(["2025-01-02", "2025-01-03"])}).to_parquet(
        meta / "trade_days.parquet", index=False
    )
    snapshot = tmp_path / "snapshots" / "as_of=2025-01-02"
    snapshot.mkdir(parents=True)
    pd.DataFrame(
        {"industry_code": ["801080"], "code": ["000001.XSHE"]}
    ).to_parquet(snapshot / "industry_members.parquet", index=False)
    pd.DataFrame(
        {
            "code": ["000001.XSHE"],
            "display_name": ["示例"],
            "start_date": pd.to_datetime(["2000-01-01"]),
            "end_date": pd.to_datetime(["2200-01-01"]),
        }
    ).to_parquet(snapshot / "security_master.parquet", index=False)
    pd.DataFrame({"code": ["000001.XSHE"], "is_st": [False]}).to_parquet(
        snapshot / "st_status.parquet", index=False
    )
    pd.DataFrame({"code": ["000001.XSHE"], "roe": [10.0]}).to_parquet(
        snapshot / "fundamentals.parquet", index=False
    )
    bars = tmp_path / "daily_bars" / "year=2025" / "month=01"
    bars.mkdir(parents=True)
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02"]),
            "code": ["000001.XSHE"],
            "close": [10.5],
        }
    ).to_parquet(bars / "bars.parquet", index=False)

    source = ParquetDataSource(tmp_path)

    assert source.trade_days(date(2025, 1, 1), date(2025, 1, 2)) == [date(2025, 1, 2)]
    assert source.industry_stocks(["801080"], date(2025, 1, 2)) == ["000001.XSHE"]
    assert source.security_master(["000001.XSHE"], date(2025, 1, 2)).iloc[0][
        "display_name"
    ] == "示例"
    assert not source.st_status(["000001.XSHE"], date(2025, 1, 2)).iloc[0]
    assert source.fundamentals(
        ["000001.XSHE"], date(2025, 1, 2), ["roe"]
    ).iloc[0]["roe"] == 10.0
    assert source.daily_bars(
        ["000001.XSHE"], date(2025, 1, 2), date(2025, 1, 2), ["close"]
    ).iloc[0]["close"] == 10.5
