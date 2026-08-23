import json

import pandas as pd
import pytest

from jquant.visualization import load_backtest_output, plot_backtest_output


def write_sample_output(directory: object) -> None:
    dates = pd.bdate_range("2025-01-02", periods=45)
    equity = pd.DataFrame(
        {
            "date": dates,
            "equity": [100_000 + index * 500 for index in range(len(dates))],
            "cash": [2_000.0] * len(dates),
            "market_value": [98_000 + index * 500 for index in range(len(dates))],
            "benchmark": [4_000 + index * 5 for index in range(len(dates))],
            "daily_return": [0.0] * len(dates),
        }
    )
    equity.to_csv(directory / "equity_curve.csv", index=False)
    pd.DataFrame(
        [
            {
                "date": dates[0],
                "code": "000001.XSHE",
                "side": "buy",
                "shares": 100,
                "price": 10,
                "notional": 1_000,
                "fees": 5,
                "status": "filled",
                "reason": "",
            }
        ]
    ).to_csv(directory / "orders.csv", index=False)
    pd.DataFrame(
        [
            {
                "signal_date": dates[0],
                "execution_date": dates[1],
                "targets": "000001.XSHE",
            }
        ]
    ).to_csv(directory / "rebalance_plans.csv", index=False)
    (directory / "metrics.json").write_text(
        json.dumps(
            {
                "total_return": 0.22,
                "annual_return": 0.3,
                "annual_volatility": 0.2,
                "sharpe_ratio": 1.4,
                "max_drawdown": -0.05,
                "benchmark_return": 0.08,
                "excess_return": 0.14,
                "final_equity": 122_000,
            }
        ),
        encoding="utf-8",
    )


def test_load_and_plot_backtest_output(tmp_path) -> None:
    write_sample_output(tmp_path)

    loaded = load_backtest_output(tmp_path)
    destination = plot_backtest_output(tmp_path, dpi=80)

    assert len(loaded.equity_curve) == 45
    assert loaded.metrics["total_return"] == 0.22
    assert destination.is_file()
    assert destination.stat().st_size > 10_000


def test_load_requires_equity_curve(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="equity_curve"):
        load_backtest_output(tmp_path)
