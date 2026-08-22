from jquant.backtest.costs import TransactionCostModel
from jquant.config import CostConfig


def test_sell_cost_includes_stamp_duty() -> None:
    model = TransactionCostModel(
        CostConfig(
            commission_rate=0.0003,
            minimum_commission=5,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
        )
    )

    assert model.fees(10_000, "buy") == 5.1
    assert model.fees(10_000, "sell") == 10.1


def test_affordable_shares_respects_lot_and_fees() -> None:
    model = TransactionCostModel(CostConfig(lot_size=100, minimum_commission=5))

    assert model.affordable_shares(10_004, 10.0, 1_000) == 900

