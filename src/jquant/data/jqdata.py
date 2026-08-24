from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from datetime import date
from importlib import import_module
from typing import Any

import pandas as pd


class JQDataSource:
    """Thin adapter around jqdatasdk; no strategy logic belongs here."""

    def __init__(self, username: str | None = None, password: str | None = None) -> None:
        self._jq = import_module("jqdatasdk")
        user = username or os.getenv("JQDATA_USERNAME")
        secret = password or os.getenv("JQDATA_PASSWORD")
        if not user or not secret:
            raise RuntimeError(
                "缺少聚宽凭据，请设置 JQDATA_USERNAME 和 JQDATA_PASSWORD 环境变量"
            )
        try:
            self._jq.auth(user, secret)
            authenticated = self._jq.is_auth()
        except Exception as exc:
            if "未开通权限" in str(exc):
                raise RuntimeError(
                    "该账号尚未开通 JQData SDK 本地调用权限，请先访问 "
                    "https://www.joinquant.com/default/index/sdk 提交申请"
                ) from None
            raise RuntimeError("JQData 认证失败，请检查网络、账号及密码") from exc
        if not authenticated:
            raise RuntimeError("JQData 认证失败，请检查账号、密码及数据权限")

    def trade_days(self, start: date, end: date) -> list[date]:
        days = self._jq.get_trade_days(start_date=str(start), end_date=str(end))
        return [pd.Timestamp(day).date() for day in days]

    def industry_stocks(self, industry_codes: Sequence[str], as_of: date) -> list[str]:
        stocks: set[str] = set()
        for industry_code in industry_codes:
            stocks.update(self._jq.get_industry_stocks(industry_code, date=str(as_of)))
        return sorted(stocks)

    def security_master(self, codes: Sequence[str], as_of: date) -> pd.DataFrame:
        if not codes:
            return pd.DataFrame(columns=["display_name", "start_date", "end_date"])
        frame = self._jq.get_all_securities(types=["stock"], date=str(as_of)).copy()
        frame.index = frame.index.astype(str)
        frame.index.name = "code"
        selected = frame.reindex(list(codes))
        for column in ("start_date", "end_date"):
            if column in selected:
                selected[column] = pd.to_datetime(selected[column]).dt.date
        return selected

    def st_status(self, codes: Sequence[str], as_of: date) -> pd.Series:
        if not codes:
            return pd.Series(dtype=bool, name="is_st")
        result = self._jq.get_extras(
            "is_st",
            list(codes),
            start_date=str(as_of),
            end_date=str(as_of),
            df=True,
        )
        if result.empty:
            return pd.Series(False, index=list(codes), name="is_st")
        status = result.iloc[-1].reindex(list(codes)).fillna(False).astype(bool)
        status.name = "is_st"
        return status

    def fundamentals(
        self,
        codes: Sequence[str],
        as_of: date,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        columns = list(dict.fromkeys(fields))
        if not codes:
            return pd.DataFrame(columns=columns).rename_axis("code")
        if not columns:
            return pd.DataFrame(index=pd.Index(codes, name="code"))
        jq = self._jq
        field_map = {
            "market_cap": (jq.valuation.market_cap, "market_cap"),
            "circulating_market_cap": (
                jq.valuation.circulating_market_cap,
                "circulating_market_cap",
            ),
            "pe_ratio": (jq.valuation.pe_ratio, "pe_ratio"),
            "pb_ratio": (jq.valuation.pb_ratio, "pb_ratio"),
            "roe": (jq.indicator.roe, "roe"),
            "revenue_growth": (
                jq.indicator.inc_revenue_year_on_year,
                "inc_revenue_year_on_year",
            ),
            "net_profit_growth": (
                jq.indicator.inc_net_profit_year_on_year,
                "inc_net_profit_year_on_year",
            ),
            "total_assets": (jq.balance.total_assets, "total_assets"),
            "total_liability": (jq.balance.total_liability, "total_liability"),
        }
        unknown = set(columns) - set(field_map)
        if unknown:
            raise ValueError(f"不支持的基本面字段: {sorted(unknown)}")

        frames: list[pd.DataFrame] = []
        for chunk in _chunks(codes, 800):
            expressions = [field_map[field][0] for field in columns]
            query = jq.query(jq.valuation.code, *expressions).filter(
                jq.valuation.code.in_(chunk)
            )
            frames.append(jq.get_fundamentals(query, date=str(as_of)))
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if frame.empty:
            return pd.DataFrame(columns=columns).rename_axis("code")
        rename_map = {source_name: field for field, (_, source_name) in field_map.items()}
        frame = frame.rename(columns=rename_map)
        return frame.set_index("code")[columns].sort_index()

    def daily_bars(
        self,
        codes: Sequence[str],
        start: date,
        end: date,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        if not codes:
            return _empty_bars(fields)
        frames: list[pd.DataFrame] = []
        for chunk in _chunks(codes, 500):
            raw = self._jq.get_price(
                list(chunk),
                start_date=str(start),
                end_date=str(end),
                frequency="daily",
                fields=list(fields),
                skip_paused=False,
                fq="pre",
                panel=False,
            )
            frames.append(_normalize_price_frame(raw, chunk, fields))
        if not frames:
            return _empty_bars(fields)
        combined = pd.concat(frames).sort_index()
        return combined[~combined.index.duplicated(keep="last")]

    def query_count(self) -> dict[str, Any]:
        return self._jq.get_query_count()

    def has_daily_access(self, code: str, on_date: date) -> bool:
        """Return whether one known liquid security can be read on a trading day."""
        try:
            frame = self._jq.get_price(
                code,
                start_date=str(on_date),
                end_date=str(on_date),
                frequency="daily",
                fields=["close"],
                skip_paused=False,
                fq="pre",
                panel=False,
            )
        except Exception:
            return False
        return bool(
            isinstance(frame, pd.DataFrame)
            and not frame.empty
            and "close" in frame
            and frame["close"].notna().any()
        )


def _chunks(values: Sequence[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def _empty_bars(fields: Sequence[str]) -> pd.DataFrame:
    index = pd.MultiIndex.from_arrays([[], []], names=["date", "code"])
    return pd.DataFrame(columns=list(fields), index=index)


def _normalize_price_frame(
    raw: pd.DataFrame, codes: Sequence[str], fields: Sequence[str]
) -> pd.DataFrame:
    frame = raw.copy()
    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.reset_index()
    elif "time" not in frame.columns and "date" not in frame.columns:
        frame = frame.reset_index()

    date_column = next(
        (name for name in ("time", "date", "index", "level_0") if name in frame.columns),
        None,
    )
    if date_column is None:
        raise ValueError("无法识别 jqdatasdk 行情返回值中的日期列")
    if "code" not in frame.columns:
        if len(codes) != 1:
            raise ValueError("多标的行情返回值缺少 code 列")
        frame["code"] = codes[0]
    frame["date"] = pd.to_datetime(frame[date_column]).dt.normalize()
    frame["code"] = frame["code"].astype(str)
    missing = set(fields) - set(frame.columns)
    if missing:
        raise ValueError(f"行情返回值缺少字段: {sorted(missing)}")
    return frame.set_index(["date", "code"])[list(fields)].sort_index()
