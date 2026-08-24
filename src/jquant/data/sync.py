from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd

from jquant.config import StrategyConfig
from jquant.data.base import MarketData

DAILY_FIELDS = ("open", "close", "money", "paused", "high_limit", "low_limit")
FUNDAMENTAL_FIELDS = (
    "market_cap",
    "circulating_market_cap",
    "pe_ratio",
    "pb_ratio",
    "roe",
    "revenue_growth",
    "net_profit_growth",
    "total_assets",
    "total_liability",
)
ACCESS_PROBE_CODE = "000300.XSHG"


class SynchronizableMarketData(MarketData, Protocol):
    def has_daily_access(self, code: str, on_date: date) -> bool: ...

    def query_count(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class SyncSummary:
    access_start: str
    access_end: str
    snapshot_count: int
    security_count: int
    daily_bar_rows: int
    output: str


def detect_access_range(
    source: SynchronizableMarketData,
    today: date | None = None,
) -> tuple[date, date]:
    """Find the contiguous daily-price interval available to the account."""
    current = today or date.today()
    days = source.trade_days(date(2005, 1, 1), current)
    if not days:
        raise RuntimeError("无法读取交易日历")

    expected = _shift_months(current, -9)
    anchor_index = min(range(len(days)), key=lambda index: abs(days[index] - expected))
    if not source.has_daily_access(ACCESS_PROBE_CODE, days[anchor_index]):
        candidates = sorted(
            range(len(days)), key=lambda index: abs(days[index] - expected)
        )
        anchor_index = next(
            (
                index
                for index in candidates[::20]
                if source.has_daily_access(ACCESS_PROBE_CODE, days[index])
            ),
            -1,
        )
        if anchor_index < 0:
            raise RuntimeError("未探测到可读取的日线行情日期")

    first = _first_accessible(source, days, anchor_index)
    last = _last_accessible(source, days, anchor_index)
    return days[first], days[last]


def sync_strategy_data(
    source: SynchronizableMarketData,
    config: StrategyConfig,
    output: str | Path,
    today: date | None = None,
) -> SyncSummary:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    access_start, access_end = detect_access_range(source, today=today)
    trade_days = source.trade_days(access_start, access_end)
    if not trade_days:
        raise RuntimeError("权限区间内没有交易日")
    _write_parquet(
        pd.DataFrame({"date": pd.to_datetime(trade_days)}),
        root / "meta" / "trade_days.parquet",
    )

    snapshot_dates = _month_end_days(trade_days)
    all_strategy_codes: set[str] = set()
    for snapshot_date in snapshot_dates:
        snapshot_root = root / "snapshots" / f"as_of={snapshot_date.isoformat()}"
        member_rows: list[dict[str, str]] = []
        for industry_code in config.industry_codes:
            codes = source.industry_stocks([industry_code], snapshot_date)
            member_rows.extend(
                {"industry_code": industry_code, "code": code} for code in codes
            )
        members = pd.DataFrame(member_rows, columns=["industry_code", "code"])
        members = members.drop_duplicates().sort_values(["industry_code", "code"])
        codes = sorted(members["code"].unique().tolist()) if not members.empty else []
        all_strategy_codes.update(codes)
        _write_parquet(members, snapshot_root / "industry_members.parquet")

        master = source.security_master(codes, snapshot_date).reset_index()
        _write_parquet(master, snapshot_root / "security_master.parquet")
        st = source.st_status(codes, snapshot_date).rename("is_st").rename_axis("code")
        _write_parquet(st.reset_index(), snapshot_root / "st_status.parquet")
        fundamentals = source.fundamentals(
            codes, snapshot_date, FUNDAMENTAL_FIELDS
        ).reset_index()
        _write_parquet(fundamentals, snapshot_root / "fundamentals.parquet")

    bar_codes = sorted(all_strategy_codes | {ACCESS_PROBE_CODE})
    daily_bar_rows = 0
    for month_start, month_end in _month_ranges(access_start, access_end):
        bars = source.daily_bars(
            bar_codes, month_start, month_end, fields=DAILY_FIELDS
        ).reset_index()
        daily_bar_rows += len(bars)
        destination = (
            root
            / "daily_bars"
            / f"year={month_start.year:04d}"
            / f"month={month_start.month:02d}"
            / "bars.parquet"
        )
        _write_parquet(bars, destination)

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "JQData",
        "scope": "small_cap_tech_strategy",
        "access_start": access_start.isoformat(),
        "access_end": access_end.isoformat(),
        "industry_codes": list(config.industry_codes),
        "snapshot_dates": [value.isoformat() for value in snapshot_dates],
        "daily_fields": list(DAILY_FIELDS),
        "fundamental_fields": list(FUNDAMENTAL_FIELDS),
        "security_count": len(all_strategy_codes),
        "daily_bar_rows": daily_bar_rows,
        "query_count_after": source.query_count(),
    }
    _write_json(manifest, root / "manifest.json")
    return SyncSummary(
        access_start=access_start.isoformat(),
        access_end=access_end.isoformat(),
        snapshot_count=len(snapshot_dates),
        security_count=len(all_strategy_codes),
        daily_bar_rows=daily_bar_rows,
        output=str(root.resolve()),
    )


def summary_json(summary: SyncSummary) -> str:
    return json.dumps(asdict(summary), ensure_ascii=False, indent=2)


def _first_accessible(
    source: SynchronizableMarketData, days: list[date], accessible: int
) -> int:
    if source.has_daily_access(ACCESS_PROBE_CODE, days[0]):
        return 0
    low, high = 0, accessible
    while low + 1 < high:
        middle = (low + high) // 2
        if source.has_daily_access(ACCESS_PROBE_CODE, days[middle]):
            high = middle
        else:
            low = middle
    return high


def _last_accessible(
    source: SynchronizableMarketData, days: list[date], accessible: int
) -> int:
    if source.has_daily_access(ACCESS_PROBE_CODE, days[-1]):
        return len(days) - 1
    low, high = accessible, len(days) - 1
    while low + 1 < high:
        middle = (low + high) // 2
        if source.has_daily_access(ACCESS_PROBE_CODE, days[middle]):
            low = middle
        else:
            high = middle
    return low


def _month_end_days(days: list[date]) -> list[date]:
    result: list[date] = []
    for index, value in enumerate(days):
        if index == len(days) - 1 or (
            value.year,
            value.month,
        ) != (days[index + 1].year, days[index + 1].month):
            result.append(value)
    return result


def _month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        first = max(start, date(year, month, 1))
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        last = min(end, next_month - pd.Timedelta(days=1))
        ranges.append((first, last))
        year, month = next_month.year, next_month.month
    return ranges


def _shift_months(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(absolute, 12)
    month = month_index + 1
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last_day = (next_month - pd.Timedelta(days=1)).day
    return date(year, month, min(value.day, last_day))


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)


def _write_json(value: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
