from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestOutput:
    equity_curve: pd.DataFrame
    metrics: dict[str, float | None]
    orders: pd.DataFrame
    rebalance_plans: pd.DataFrame


def load_backtest_output(input_dir: str | Path) -> BacktestOutput:
    source = Path(input_dir)
    equity_path = source / "equity_curve.csv"
    if not equity_path.is_file():
        raise FileNotFoundError(f"缺少回测净值文件: {equity_path}")

    equity = pd.read_csv(equity_path, parse_dates=["date"]).set_index("date").sort_index()
    required = {"equity", "cash", "market_value", "benchmark"}
    missing = required - set(equity.columns)
    if missing:
        raise ValueError(f"equity_curve.csv 缺少字段: {sorted(missing)}")
    if equity.empty:
        raise ValueError("equity_curve.csv 没有数据")
    if equity.index.has_duplicates:
        raise ValueError("equity_curve.csv 包含重复日期")

    metrics_path = source / "metrics.json"
    metrics = (
        json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics_path.is_file()
        else {}
    )
    orders = _read_optional_csv(source / "orders.csv", parse_dates=["date"])
    plans = _read_optional_csv(
        source / "rebalance_plans.csv", parse_dates=["signal_date", "execution_date"]
    )
    return BacktestOutput(equity, metrics, orders, plans)


def plot_backtest_output(
    input_dir: str | Path,
    output_path: str | Path | None = None,
    *,
    show: bool = False,
    dpi: int = 160,
) -> Path:
    if "MPLCONFIGDIR" not in os.environ:
        matplotlib_cache = Path(tempfile.gettempdir()) / "jquant-matplotlib-cache"
        matplotlib_cache.mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(matplotlib_cache)
    import matplotlib

    if not show:
        matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    data = load_backtest_output(input_dir)
    equity = data.equity_curve
    destination = Path(output_path) if output_path else Path(input_dir) / "backtest_report.png"
    destination.parent.mkdir(parents=True, exist_ok=True)

    _configure_style(plt)
    figure = plt.figure(figsize=(14, 10), constrained_layout=True)
    grid = figure.add_gridspec(3, 2, height_ratios=(1.35, 1.0, 0.9))
    equity_axis = figure.add_subplot(grid[0, :])
    drawdown_axis = figure.add_subplot(grid[1, 0])
    monthly_axis = figure.add_subplot(grid[1, 1])
    exposure_axis = figure.add_subplot(grid[2, 0])
    summary_axis = figure.add_subplot(grid[2, 1])

    strategy_growth = equity["equity"] / equity["equity"].iloc[0]
    benchmark = equity["benchmark"].dropna()
    benchmark_growth = benchmark / benchmark.iloc[0] if not benchmark.empty else benchmark
    equity_axis.plot(
        strategy_growth.index,
        strategy_growth,
        color="#176B87",
        linewidth=2.2,
        label="Strategy",
    )
    if not benchmark_growth.empty:
        equity_axis.plot(
            benchmark_growth.index,
            benchmark_growth,
            color="#7A7A7A",
            linewidth=1.7,
            label="Benchmark",
        )
    if not data.rebalance_plans.empty and "execution_date" in data.rebalance_plans:
        for execution_date in data.rebalance_plans["execution_date"].dropna():
            equity_axis.axvline(execution_date, color="#D8D8D8", linewidth=0.7, alpha=0.65)
    equity_axis.set_title("Cumulative Growth", loc="left", fontweight="bold")
    equity_axis.set_ylabel("Growth of 1.0")
    equity_axis.legend(frameon=False, ncols=2, loc="upper left")
    equity_axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=10))
    equity_axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(equity_axis.xaxis.get_major_locator()))

    initial_equity = _infer_initial_equity(equity, data.metrics)
    peaks = equity["equity"].cummax().clip(lower=initial_equity)
    drawdown = equity["equity"] / peaks - 1
    drawdown_axis.fill_between(
        drawdown.index,
        drawdown.to_numpy(dtype=float),
        0,
        color="#D95F59",
        alpha=0.35,
    )
    drawdown_axis.plot(drawdown.index, drawdown, color="#B33A3A", linewidth=1.1)
    drawdown_axis.set_title("Strategy Drawdown", loc="left", fontweight="bold")
    drawdown_axis.yaxis.set_major_formatter(PercentFormatter(1.0))

    monthly = _monthly_returns(equity)
    x = np.arange(len(monthly))
    width = 0.38
    monthly_axis.bar(
        x - width / 2,
        monthly["strategy"],
        width,
        color="#176B87",
        label="Strategy",
    )
    if monthly["benchmark"].notna().any():
        monthly_axis.bar(
            x + width / 2,
            monthly["benchmark"],
            width,
            color="#A5A5A5",
            label="Benchmark",
        )
    monthly_axis.axhline(0, color="#444444", linewidth=0.8)
    monthly_axis.set_xticks(x, monthly.index, rotation=45, ha="right")
    monthly_axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    monthly_axis.set_title("Monthly Returns", loc="left", fontweight="bold")
    monthly_axis.legend(frameon=False, ncols=2, fontsize=9)

    invested = (equity["market_value"] / equity["equity"]).clip(0, 1) * 100
    cash = (equity["cash"] / equity["equity"]).clip(0, 1) * 100
    exposure_axis.stackplot(
        equity.index,
        invested,
        cash,
        labels=("Invested", "Cash"),
        colors=("#64A6BD", "#E5E5E5"),
        alpha=0.9,
    )
    exposure_axis.set_ylim(0, 100)
    exposure_axis.set_title("Portfolio Exposure", loc="left", fontweight="bold")
    exposure_axis.set_ylabel("Percent")
    exposure_axis.legend(frameon=False, ncols=2, loc="lower left")
    exposure_axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    exposure_axis.xaxis.set_major_formatter(
        mdates.ConciseDateFormatter(exposure_axis.xaxis.get_major_locator())
    )

    summary_axis.axis("off")
    summary_axis.set_title("Run Summary", loc="left", fontweight="bold")
    summary_axis.text(
        0.0,
        0.92,
        _summary_text(data),
        transform=summary_axis.transAxes,
        va="top",
        ha="left",
        fontsize=11,
        linespacing=1.55,
        family="monospace",
    )

    start = equity.index.min().date().isoformat()
    end = equity.index.max().date().isoformat()
    figure.suptitle(
        f"Technology Small-Cap Backtest  |  {start} to {end}",
        fontsize=17,
        fontweight="bold",
    )
    figure.savefig(destination, dpi=dpi, bbox_inches="tight", facecolor=figure.get_facecolor())
    if show:
        plt.show()
    plt.close(figure)
    return destination.resolve()


def _read_optional_csv(path: Path, parse_dates: list[str]) -> pd.DataFrame:
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame()
    frame = pd.read_csv(path)
    for column in parse_dates:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column])
    return frame


def _infer_initial_equity(
    equity: pd.DataFrame, metrics: dict[str, float | None]
) -> float:
    total_return = metrics.get("total_return")
    final_equity = metrics.get("final_equity")
    if total_return is not None and final_equity is not None and total_return > -1:
        return float(final_equity) / (1 + float(total_return))
    return float(equity["equity"].iloc[0])


def _monthly_returns(equity: pd.DataFrame) -> pd.DataFrame:
    month = equity.index.to_period("M")
    strategy = equity["equity"].groupby(month).last().pct_change()
    benchmark = equity["benchmark"].groupby(month).last().pct_change()
    monthly = pd.DataFrame({"strategy": strategy, "benchmark": benchmark}).dropna(
        how="all"
    )
    monthly.index = monthly.index.astype(str)
    return monthly


def _summary_text(data: BacktestOutput) -> str:
    metrics = data.metrics
    order_count = len(data.orders)
    has_status = not data.orders.empty and "status" in data.orders
    filled_mask = data.orders["status"] == "filled" if has_status else None
    filled = int(filled_mask.sum()) if filled_mask is not None else 0
    fees = (
        float(data.orders.loc[filled_mask, "fees"].sum())
        if filled_mask is not None and "fees" in data.orders
        else 0.0
    )
    rows = [
        ("Total return", _format_percent(metrics.get("total_return"))),
        ("Annual return", _format_percent(metrics.get("annual_return"))),
        ("Volatility", _format_percent(metrics.get("annual_volatility"))),
        ("Sharpe ratio", _format_number(metrics.get("sharpe_ratio"))),
        ("Max drawdown", _format_percent(metrics.get("max_drawdown"))),
        ("Benchmark", _format_percent(metrics.get("benchmark_return"))),
        ("Excess return", _format_percent(metrics.get("excess_return"))),
        ("Orders", f"{filled}/{order_count} filled"),
        ("Fees", f"CNY {fees:,.2f}"),
    ]
    return "\n".join(f"{label:<16} {value:>16}" for label, value in rows)


def _format_percent(value: float | None) -> str:
    return "N/A" if value is None else f"{float(value):.2%}"


def _format_number(value: float | None) -> str:
    return "N/A" if value is None else f"{float(value):.2f}"


def _configure_style(plt: object) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "axes.facecolor": "#FAFAF8",
            "figure.facecolor": "#FAFAF8",
            "axes.edgecolor": "#C8C8C8",
            "axes.grid": True,
            "grid.alpha": 0.24,
            "grid.linewidth": 0.7,
            "font.size": 10,
        }
    )
