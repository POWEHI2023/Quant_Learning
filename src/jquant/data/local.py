from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pandas as pd

from jquant.data.jqdata import _empty_bars


class ParquetDataSource:
    """Read-only market-data adapter backed by a synchronized Parquet directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        if not (self.root / "manifest.json").is_file():
            raise RuntimeError(f"本地数据目录缺少 manifest.json: {self.root}")

    def trade_days(self, start: date, end: date) -> list[date]:
        frame = pd.read_parquet(self.root / "meta" / "trade_days.parquet")
        values = pd.to_datetime(frame["date"]).dt.date
        return [value for value in values if start <= value <= end]

    def industry_stocks(self, industry_codes: Sequence[str], as_of: date) -> list[str]:
        frame = self._read_snapshot(as_of, "industry_members.parquet")
        selected = frame[frame["industry_code"].isin(industry_codes)]
        return sorted(selected["code"].astype(str).unique().tolist())

    def security_master(self, codes: Sequence[str], as_of: date) -> pd.DataFrame:
        if not codes:
            return pd.DataFrame(columns=["display_name", "start_date", "end_date"])
        frame = self._read_snapshot(as_of, "security_master.parquet").copy()
        frame["code"] = frame["code"].astype(str)
        for column in ("start_date", "end_date"):
            if column in frame:
                frame[column] = pd.to_datetime(frame[column]).dt.date
        return frame.set_index("code").reindex(list(codes))

    def st_status(self, codes: Sequence[str], as_of: date) -> pd.Series:
        if not codes:
            return pd.Series(dtype=bool, name="is_st")
        frame = self._read_snapshot(as_of, "st_status.parquet")
        values = frame.set_index("code")["is_st"].astype(bool)
        return values.reindex(list(codes)).fillna(False).rename("is_st")

    def fundamentals(
        self,
        codes: Sequence[str],
        as_of: date,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        columns = list(dict.fromkeys(fields))
        if not codes:
            return pd.DataFrame(columns=columns).rename_axis("code")
        frame = self._read_snapshot(as_of, "fundamentals.parquet")
        missing = set(columns) - set(frame.columns)
        if missing:
            raise ValueError(f"本地基本面数据缺少字段: {sorted(missing)}")
        return frame.set_index("code").reindex(list(codes))[columns]

    def daily_bars(
        self,
        codes: Sequence[str],
        start: date,
        end: date,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        if not codes:
            return _empty_bars(fields)
        paths = self._bar_paths(start, end)
        if not paths:
            return _empty_bars(fields)
        requested = set(codes)
        frames: list[pd.DataFrame] = []
        for path in paths:
            frame = pd.read_parquet(path, columns=["date", "code", *fields])
            timestamps = pd.to_datetime(frame["date"])
            mask = (
                frame["code"].astype(str).isin(requested)
                & (timestamps.dt.date >= start)
                & (timestamps.dt.date <= end)
            )
            frames.append(frame.loc[mask].assign(date=timestamps.loc[mask]))
        if not frames:
            return _empty_bars(fields)
        combined = pd.concat(frames, ignore_index=True)
        if combined.empty:
            return _empty_bars(fields)
        combined["code"] = combined["code"].astype(str)
        return combined.set_index(["date", "code"])[list(fields)].sort_index()

    def _read_snapshot(self, as_of: date, name: str) -> pd.DataFrame:
        path = self.root / "snapshots" / f"as_of={as_of.isoformat()}" / name
        if not path.is_file():
            raise RuntimeError(f"本地数据缺少 {as_of} 的快照: {name}")
        return pd.read_parquet(path)

    def _bar_paths(self, start: date, end: date) -> list[Path]:
        paths: list[Path] = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            path = (
                self.root
                / "daily_bars"
                / f"year={year:04d}"
                / f"month={month:02d}"
                / "bars.parquet"
            )
            if path.is_file():
                paths.append(path)
            month += 1
            if month == 13:
                year += 1
                month = 1
        return paths
