from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any, TypeVar

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib


@dataclass(frozen=True)
class BacktestConfig:
    start_date: date
    end_date: date
    initial_cash: float = 1_000_000.0
    benchmark: str = "000300.XSHG"
    rebalance: str = "monthly"


@dataclass(frozen=True)
class StrategyConfig:
    industry_codes: tuple[str, ...] = ("801080", "801750", "801770")
    hold_count: int = 10
    min_listing_days: int = 250
    liquidity_lookback_days: int = 20
    min_average_turnover: float = 10_000_000.0
    allowed_exchange_suffixes: tuple[str, ...] = ("XSHG", "XSHE")
    cash_buffer: float = 0.02


@dataclass(frozen=True)
class CostConfig:
    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    stamp_duty_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    slippage_bps: float = 5.0
    lot_size: int = 100


@dataclass(frozen=True)
class MetricsConfig:
    risk_free_rate: float = 0.02
    annual_trading_days: int = 252


@dataclass(frozen=True)
class AppConfig:
    backtest: BacktestConfig
    strategy: StrategyConfig
    costs: CostConfig
    metrics: MetricsConfig


T = TypeVar("T")


def _only_known(cls: type[T], values: dict[str, Any]) -> dict[str, Any]:
    known = {field.name for field in fields(cls)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"{cls.__name__} 包含未知配置项: {sorted(unknown)}")
    return values


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as stream:
        raw = tomllib.load(stream)

    required_sections = {"backtest", "strategy", "costs", "metrics"}
    missing = required_sections - set(raw)
    if missing:
        raise ValueError(f"缺少配置段: {sorted(missing)}")

    backtest_raw = _only_known(BacktestConfig, dict(raw["backtest"]))
    strategy_raw = _only_known(StrategyConfig, dict(raw["strategy"]))
    costs_raw = _only_known(CostConfig, dict(raw["costs"]))
    metrics_raw = _only_known(MetricsConfig, dict(raw["metrics"]))

    backtest_raw["start_date"] = date.fromisoformat(backtest_raw["start_date"])
    backtest_raw["end_date"] = date.fromisoformat(backtest_raw["end_date"])
    for key in ("industry_codes", "allowed_exchange_suffixes"):
        if key in strategy_raw:
            strategy_raw[key] = tuple(strategy_raw[key])

    config = AppConfig(
        backtest=BacktestConfig(**backtest_raw),
        strategy=StrategyConfig(**strategy_raw),
        costs=CostConfig(**costs_raw),
        metrics=MetricsConfig(**metrics_raw),
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    bt, strategy, costs = config.backtest, config.strategy, config.costs
    if bt.start_date >= bt.end_date:
        raise ValueError("start_date 必须早于 end_date")
    if bt.initial_cash <= 0:
        raise ValueError("initial_cash 必须大于 0")
    if bt.rebalance != "monthly":
        raise ValueError("第一版仅支持 monthly 调仓")
    if strategy.hold_count <= 0 or strategy.liquidity_lookback_days <= 0:
        raise ValueError("持仓数和流动性回看天数必须大于 0")
    if not 0 <= strategy.cash_buffer < 1:
        raise ValueError("cash_buffer 必须位于 [0, 1)")
    if costs.lot_size <= 0:
        raise ValueError("lot_size 必须大于 0")
    for value in (
        costs.commission_rate,
        costs.minimum_commission,
        costs.stamp_duty_rate,
        costs.transfer_fee_rate,
        costs.slippage_bps,
    ):
        if value < 0:
            raise ValueError("交易成本参数不能为负数")

